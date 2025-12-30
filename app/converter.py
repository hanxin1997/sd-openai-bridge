import base64
import httpx
import json
import asyncio
import re
from typing import Dict, Any, Optional, Tuple
from .logger import logger
from .config import load_config, get_available_api, update_api_status, APIEndpoint


def safe_int(value, default=0):
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


class SDToOpenAIConverter:
    """SD API 请求转换为 OpenAI API 请求"""
    
    @staticmethod
    def build_prompt(sd_request: Dict[str, Any]) -> str:
        prompt = sd_request.get("prompt", "")
        negative_prompt = sd_request.get("negative_prompt", "")
        
        if negative_prompt:
            return f"{prompt} --no {negative_prompt}"
        return prompt
    
    @staticmethod
    def convert_request(sd_request: Dict[str, Any], model: str) -> Dict[str, Any]:
        """转换 SD 请求为 OpenAI 格式"""
        prompt = SDToOpenAIConverter.build_prompt(sd_request)
        
        openai_request = {
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "model": model
        }
        
        logger.info(f"Model: {model}")
        logger.info(f"Prompt: {prompt[:100]}..." if len(prompt) > 100 else f"Prompt: {prompt}")
        
        return openai_request
    
    @staticmethod
    def extract_image_urls(content: str) -> list:
        """从 Markdown 内容中提取图片 URL"""
        urls = []
        
        # 匹配 ![xxx](url)
        pattern = r'!\[.*?\]\((https?://[^\s\)]+)\)'
        matches = re.findall(pattern, content)
        urls.extend(matches)
        
        # 备用：直接匹配图片 URL
        if not urls:
            url_pattern = r'(https?://[^\s\)\"\'<>]+\.(?:png|jpg|jpeg|webp|gif)(?:\?[^\s\)\"\'<>]*)?)'
            matches = re.findall(url_pattern, content, re.IGNORECASE)
            urls.extend(matches)
        
        return [url.rstrip(')') for url in urls]
    
    @staticmethod
    async def convert_response(openai_response: Dict[str, Any], original_request: Dict[str, Any]) -> Dict[str, Any]:
        """转换 OpenAI 响应为 SD 格式"""
        images = []
        
        try:
            # 处理 choices 格式
            if "choices" in openai_response:
                for choice in openai_response.get("choices", []):
                    message = choice.get("message", {})
                    content = message.get("content", "")
                    
                    if isinstance(content, str):
                        urls = SDToOpenAIConverter.extract_image_urls(content)
                        logger.info(f"提取到 {len(urls)} 个图片URL")
                        
                        for url in urls:
                            logger.info(f"下载图片: {url[:80]}...")
                            base64_img = await SDToOpenAIConverter.download_image(url)
                            if base64_img:
                                images.append(base64_img)
                                logger.info("下载成功")
                            else:
                                logger.warning("下载失败")
            
            # 处理 data 格式（兼容 DALL-E 风格）
            if "data" in openai_response:
                for item in openai_response["data"]:
                    if "url" in item:
                        base64_img = await SDToOpenAIConverter.download_image(item["url"])
                        if base64_img:
                            images.append(base64_img)
                    elif "b64_json" in item:
                        images.append(item["b64_json"])
                    
        except Exception as e:
            logger.error(f"响应解析失败: {str(e)}")
        
        sd_response = {
            "images": images,
            "parameters": original_request,
            "info": json.dumps({
                "prompt": original_request.get("prompt", ""),
                "negative_prompt": original_request.get("negative_prompt", ""),
                "seed": safe_int(original_request.get("seed", -1), -1),
                "width": safe_int(original_request.get("width", 1024), 1024),
                "height": safe_int(original_request.get("height", 1024), 1024),
                "steps": safe_int(original_request.get("steps", 20), 20),
                "cfg_scale": safe_float(original_request.get("cfg_scale", 7), 7),
                "sampler_name": original_request.get("sampler_name", "Euler"),
            })
        }
        
        logger.info(f"转换完成, 共 {len(images)} 张图片")
        
        return sd_response
    
    @staticmethod
    async def download_image(url: str) -> Optional[str]:
        """下载图片并转为 base64"""
        try:
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    return base64.b64encode(response.content).decode('utf-8')
                else:
                    logger.error(f"下载失败 HTTP {response.status_code}")
        except Exception as e:
            logger.error(f"下载异常: {str(e)}")
        return None


class OpenAIClient:
    """OpenAI API 客户端"""
    
    @staticmethod
    async def call(openai_request: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
        """调用上游 OpenAI API"""
        config = load_config()
        
        api = get_available_api()
        if not api:
            logger.error("没有可用的API端点")
            return {"error": "没有可用的API端点"}, None
        
        logger.info(f"使用API: [{api.name}] (已用 {api.success_count}/{api.max_success_count})")
        
        # 设置正确的 model
        request = {
            "messages": openai_request.get("messages", []),
            "model": api.model
        }
        
        retry_count = safe_int(config.request_retry_count, 2)
        retry_delay = safe_float(config.request_retry_delay, 1.0)
        
        for attempt in range(retry_count + 1):
            try:
                result = await OpenAIClient._request(api, request, config)
                
                if "error" not in result:
                    update_api_status(api.id, success=True)
                    logger.info(f"[{api.name}] ✅ 请求成功")
                    return result, api.id
                else:
                    logger.warning(f"[{api.name}] 错误: {result['error']}")
                    
            except Exception as e:
                logger.warning(f"[{api.name}] 异常: {str(e)}")
            
            if attempt < retry_count:
                logger.info(f"重试 {attempt + 1}/{retry_count}...")
                await asyncio.sleep(retry_delay)
        
        # 记录失败
        update_api_status(api.id, success=False)
        
        # 尝试下一个 API
        next_api = get_available_api()
        if next_api and next_api.id != api.id:
            logger.info(f"切换到: [{next_api.name}]")
            return await OpenAIClient.call(openai_request)
        
        return {"error": f"[{api.name}] 所有重试均失败"}, api.id
    
    @staticmethod
    async def _request(api: APIEndpoint, request: Dict[str, Any], config) -> Dict[str, Any]:
        """发送 HTTP 请求"""
        headers = {"Content-Type": "application/json"}
        
        if api.api_key:
            headers["Authorization"] = f"Bearer {api.api_key}"
        
        logger.info(f"POST {api.api_url}")
        logger.debug(f"请求体: {json.dumps(request, ensure_ascii=False)[:300]}")
        
        timeout = safe_int(config.timeout, 300)
        
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.post(api.api_url, headers=headers, json=request)
            
            logger.info(f"响应状态: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                logger.debug(f"响应体: {json.dumps(result, ensure_ascii=False)[:300]}")
                return result
            else:
                error_text = response.text[:300]
                logger.error(f"错误响应: {error_text}")
                return {"error": f"HTTP {response.status_code}: {error_text}"}