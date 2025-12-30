from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import json
from datetime import datetime

from .config import APIEndpoint, load_config, save_config, get_current_api, switch_to_api
from .converter import SDToOpenAIConverter, OpenAIClient
from .logger import logger, get_logs, clear_logs

app = FastAPI(title="SD-OpenAI Bridge", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 配置 API ====================

@app.get("/api/config")
async def api_get_config():
    config = load_config()
    current_api = get_current_api()
    
    endpoints_info = []
    for api in config.api_endpoints:
        ban_remaining = None
        if api.is_banned and api.banned_until:
            try:
                ban_time = datetime.fromisoformat(api.banned_until)
                remaining = (ban_time - datetime.now()).total_seconds()
                ban_remaining = int(remaining) if remaining > 0 else None
            except:
                pass
        
        endpoints_info.append({
            "id": api.id,
            "name": api.name,
            "api_url": api.api_url,
            "api_key": api.api_key,
            "model": api.model,
            "enabled": api.enabled,
            "success_count": api.success_count,
            "max_success_count": api.max_success_count,
            "consecutive_fail_count": api.consecutive_fail_count,
            "max_fail_count": api.max_fail_count,
            "is_banned": api.is_banned,
            "banned_until": api.banned_until,
            "ban_remaining_seconds": ban_remaining,
            "ban_reason": api.ban_reason,
            "total_success": api.total_success,
            "total_fail": api.total_fail,
            "is_available": api.is_available(),
            "is_current": current_api and api.id == current_api.id,
        })
    
    return {
        "api_endpoints": endpoints_info,
        "current_api_id": current_api.id if current_api else None,
        "current_api_name": current_api.name if current_api else None,
        "default_max_success_count": config.default_max_success_count,
        "default_max_fail_count": config.default_max_fail_count,
        "ban_duration_hours": config.ban_duration_hours,
        "request_retry_count": config.request_retry_count,
        "request_retry_delay": config.request_retry_delay,
        "enable_detailed_log": config.enable_detailed_log,
        "timeout": config.timeout,
    }


@app.post("/api/config")
async def api_update_config(request: Request):
    data = await request.json()
    config = load_config()
    
    if "api_endpoints" in data:
        new_endpoints = []
        for ep_data in data["api_endpoints"]:
            existing = next((e for e in config.api_endpoints if e.id == ep_data.get("id")), None)
            if existing:
                ep_data["success_count"] = existing.success_count
                ep_data["consecutive_fail_count"] = existing.consecutive_fail_count
                ep_data["total_success"] = existing.total_success
                ep_data["total_fail"] = existing.total_fail
                ep_data["is_banned"] = existing.is_banned
                ep_data["banned_until"] = existing.banned_until
                ep_data["ban_reason"] = existing.ban_reason
            new_endpoints.append(APIEndpoint(**ep_data))
        config.api_endpoints = new_endpoints
    
    for key in ["default_max_success_count", "default_max_fail_count", "ban_duration_hours",
                "request_retry_count", "request_retry_delay", "enable_detailed_log", "timeout"]:
        if key in data:
            setattr(config, key, data[key])
    
    save_config(config)
    logger.info("配置已更新")
    return {"status": "success"}


# ==================== API 端点管理 ====================

@app.post("/api/endpoints")
async def api_add_endpoint(request: Request):
    data = await request.json()
    config = load_config()
    
    new_endpoint = APIEndpoint(
        name=data.get("name", "新API"),
        api_url=data.get("api_url", ""),
        api_key=data.get("api_key", ""),
        model=data.get("model", "z-image-turbo"),
        max_success_count=data.get("max_success_count", config.default_max_success_count),
        max_fail_count=data.get("max_fail_count", config.default_max_fail_count),
    )
    config.api_endpoints.append(new_endpoint)
    save_config(config)
    
    logger.info(f"添加API: {new_endpoint.name}")
    return {"status": "success", "id": new_endpoint.id}


@app.delete("/api/endpoints/{endpoint_id}")
async def api_delete_endpoint(endpoint_id: str):
    config = load_config()
    config.api_endpoints = [ep for ep in config.api_endpoints if ep.id != endpoint_id]
    save_config(config)
    logger.info(f"删除API: {endpoint_id}")
    return {"status": "success"}


@app.post("/api/endpoints/{endpoint_id}/switch")
async def api_switch_endpoint(endpoint_id: str):
    if switch_to_api(endpoint_id):
        current = get_current_api()
        logger.info(f"切换到: {current.name if current else 'None'}")
        return {"status": "success", "current_api": current.name if current else None}
    return {"status": "error", "message": "未找到API"}


@app.post("/api/endpoints/{endpoint_id}/unban")
async def api_unban_endpoint(endpoint_id: str):
    config = load_config()
    for api in config.api_endpoints:
        if api.id == endpoint_id:
            api.unban()
            save_config(config)
            logger.info(f"解除封禁: {api.name}")
            return {"status": "success"}
    return {"status": "error", "message": "未找到API"}


@app.post("/api/endpoints/{endpoint_id}/reset")
async def api_reset_endpoint_quota(endpoint_id: str):
    config = load_config()
    for api in config.api_endpoints:
        if api.id == endpoint_id:
            api.reset_quota()
            save_config(config)
            logger.info(f"重置额度: {api.name}")
            return {"status": "success"}
    return {"status": "error", "message": "未找到API"}


@app.post("/api/endpoints/{endpoint_id}/reset-stats")
async def api_reset_endpoint_stats(endpoint_id: str):
    config = load_config()
    for api in config.api_endpoints:
        if api.id == endpoint_id:
            api.reset_stats()
            save_config(config)
            logger.info(f"重置统计: {api.name}")
            return {"status": "success"}
    return {"status": "error", "message": "未找到API"}


@app.post("/api/endpoints/reset-all")
async def api_reset_all_quotas():
    config = load_config()
    for api in config.api_endpoints:
        api.reset_quota()
    save_config(config)
    logger.info("重置所有API额度")
    return {"status": "success"}


@app.post("/api/endpoints/unban-all")
async def api_unban_all():
    config = load_config()
    for api in config.api_endpoints:
        api.unban()
    save_config(config)
    logger.info("解除所有封禁")
    return {"status": "success"}


# ==================== 日志 API ====================

@app.get("/api/logs")
async def api_get_logs():
    return {"logs": get_logs()}


@app.delete("/api/logs")
async def api_clear_logs():
    clear_logs()
    return {"status": "success"}


# ==================== SD API 兼容层 ====================

@app.post("/sdapi/v1/txt2img")
async def sdapi_txt2img(request: Request):
    try:
        sd_request = await request.json()
        
        logger.info("=" * 50)
        logger.info("txt2img 请求")
        
        config = load_config()
        if not config.api_endpoints:
            raise HTTPException(status_code=500, detail="没有配置API端点")
        
        openai_request = SDToOpenAIConverter.convert_request(sd_request, config.api_endpoints[0].model)
        openai_response, api_id = await OpenAIClient.call(openai_request)
        
        if "error" in openai_response:
            logger.error(f"上游错误: {openai_response['error']}")
            raise HTTPException(status_code=500, detail=openai_response['error'])
        
        sd_response = await SDToOpenAIConverter.convert_response(openai_response, sd_request)
        
        logger.info(f"完成: {len(sd_response['images'])} 张图片")
        logger.info("=" * 50)
        
        return JSONResponse(content=sd_response)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"错误: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sdapi/v1/img2img")
async def sdapi_img2img(request: Request):
    try:
        sd_request = await request.json()
        
        logger.info("=" * 50)
        logger.info("img2img 请求")
        
        config = load_config()
        if not config.api_endpoints:
            raise HTTPException(status_code=500, detail="没有配置API端点")
        
        openai_request = SDToOpenAIConverter.convert_request(sd_request, config.api_endpoints[0].model)
        
        init_images = sd_request.get("init_images", [])
        if init_images:
            openai_request["messages"].append({
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{init_images[0]}"}},
                    {"type": "text", "text": f"Based on this image, {sd_request.get('prompt', '')}"}
                ]
            })
        
        openai_response, api_id = await OpenAIClient.call(openai_request)
        
        if "error" in openai_response:
            raise HTTPException(status_code=500, detail=openai_response['error'])
        
        sd_response = await SDToOpenAIConverter.convert_response(openai_response, sd_request)
        
        logger.info("img2img 完成")
        logger.info("=" * 50)
        
        return JSONResponse(content=sd_response)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"错误: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== SD API 模拟端点 ====================

@app.get("/sdapi/v1/sd-models")
async def sdapi_get_models():
    return [{"title": "OpenAI-Bridge", "model_name": "openai-bridge", "hash": "abc123"}]


@app.get("/sdapi/v1/sd-vae")
async def sdapi_get_vae():
    return [{"model_name": "Automatic", "filename": "auto"}]


@app.get("/sdapi/v1/samplers")
async def sdapi_get_samplers():
    return [{"name": "Euler", "aliases": ["euler"], "options": {}}]


@app.get("/sdapi/v1/upscalers")
async def sdapi_get_upscalers():
    return [{"name": "None", "model_name": None}]


@app.get("/sdapi/v1/latent-upscale-modes")
async def sdapi_get_latent_upscale_modes():
    return [{"name": "Latent"}]


@app.get("/sdapi/v1/schedulers")
async def sdapi_get_schedulers():
    return [{"name": "automatic", "label": "Automatic"}]


@app.get("/sdapi/v1/options")
async def sdapi_get_options():
    return {"sd_model_checkpoint": "openai-bridge.safetensors"}


@app.post("/sdapi/v1/options")
async def sdapi_set_options(request: Request):
    return {"status": "success"}


@app.get("/sdapi/v1/progress")
async def sdapi_get_progress():
    return {"progress": 0, "eta_relative": 0, "state": {"job": ""}, "current_image": None}


@app.get("/sdapi/v1/cmd-flags")
async def sdapi_get_cmd_flags():
    return {}


@app.get("/sdapi/v1/embeddings")
async def sdapi_get_embeddings():
    return {"loaded": {}, "skipped": {}}


@app.get("/sdapi/v1/hypernetworks")
async def sdapi_get_hypernetworks():
    return []


@app.get("/sdapi/v1/face-restorers")
async def sdapi_get_face_restorers():
    return [{"name": "None"}]


@app.get("/sdapi/v1/realesrgan-models")
async def sdapi_get_realesrgan():
    return []


@app.get("/sdapi/v1/prompt-styles")
async def sdapi_get_styles():
    return []


@app.get("/sdapi/v1/loras")
async def sdapi_get_loras():
    return []


@app.get("/sdapi/v1/scripts")
async def sdapi_get_scripts():
    return {"txt2img": [], "img2img": []}


@app.get("/sdapi/v1/script-info")
async def sdapi_get_script_info():
    return []


@app.get("/sdapi/v1/extensions")
async def sdapi_get_extensions():
    return []


@app.post("/sdapi/v1/refresh-checkpoints")
async def sdapi_refresh_checkpoints():
    return {"status": "success"}


@app.post("/sdapi/v1/refresh-vae")
async def sdapi_refresh_vae():
    return {"status": "success"}


@app.post("/sdapi/v1/refresh-loras")
async def sdapi_refresh_loras():
    return {"status": "success"}


@app.post("/sdapi/v1/unload-checkpoint")
async def sdapi_unload_checkpoint():
    return {"status": "success"}


@app.post("/sdapi/v1/reload-checkpoint")
async def sdapi_reload_checkpoint():
    return {"status": "success"}


@app.post("/sdapi/v1/skip")
async def sdapi_skip():
    return {"status": "success"}


@app.post("/sdapi/v1/interrupt")
async def sdapi_interrupt():
    return {"status": "success"}


@app.get("/sdapi/v1/memory")
async def sdapi_get_memory():
    return {
        "ram": {"free": 8000000000, "used": 4000000000, "total": 12000000000},
        "cuda": {"free": 8000000000, "used": 4000000000, "total": 12000000000}
    }


@app.post("/sdapi/v1/png-info")
async def sdapi_png_info(request: Request):
    return {"info": "", "items": {}}


@app.post("/sdapi/v1/extra-single-image")
async def sdapi_extra_single(request: Request):
    return {"html_info": "", "image": ""}


@app.post("/sdapi/v1/extra-batch-images")
async def sdapi_extra_batch(request: Request):
    return {"html_info": "", "images": []}


@app.post("/sdapi/v1/interrogate")
async def sdapi_interrogate(request: Request):
    return {"caption": "a beautiful image"}


# ==================== 健康检查 ====================

@app.get("/")
async def root():
    return {"service": "SD-OpenAI Bridge", "version": "2.0.0", "status": "running"}


@app.get("/health")
async def health():
    config = load_config()
    current = get_current_api()
    available = len([a for a in config.api_endpoints if a.is_available()])
    return {
        "status": "healthy",
        "current_api": current.name if current else None,
        "available_apis": available,
        "total_apis": len(config.api_endpoints)
    }


@app.get("/internal/ping")
async def ping():
    return {"status": "pong"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)