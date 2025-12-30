import json
from pathlib import Path
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
import uuid

CONFIG_PATH = Path("/app/data/config.json")


class APIEndpoint(BaseModel):
    id: str = ""
    name: str = "默认API"
    api_url: str = ""
    api_key: str = ""
    model: str = "z-image-turbo"
    enabled: bool = True
    
    success_count: int = 0
    max_success_count: int = 10
    consecutive_fail_count: int = 0
    max_fail_count: int = 3
    is_banned: bool = False
    banned_until: Optional[str] = None
    ban_reason: str = ""
    total_success: int = 0
    total_fail: int = 0
    
    def __init__(self, **data):
        super().__init__(**data)
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
    
    def is_available(self) -> bool:
        if not self.enabled:
            return False
        if self.is_banned:
            if self.banned_until:
                try:
                    ban_time = datetime.fromisoformat(self.banned_until)
                    if datetime.now() >= ban_time:
                        self.is_banned = False
                        self.banned_until = None
                        self.ban_reason = ""
                        self.consecutive_fail_count = 0
                        return True
                except:
                    pass
            return False
        if self.success_count >= self.max_success_count:
            return False
        return True
    
    def record_success(self):
        self.success_count += 1
        self.total_success += 1
        self.consecutive_fail_count = 0
    
    def record_fail(self, ban_hours: int = 24) -> bool:
        self.consecutive_fail_count += 1
        self.total_fail += 1
        if self.consecutive_fail_count >= self.max_fail_count:
            self.is_banned = True
            self.banned_until = (datetime.now() + timedelta(hours=ban_hours)).isoformat()
            self.ban_reason = f"连续失败{self.consecutive_fail_count}次"
            return True
        return False
    
    def reset_quota(self):
        self.success_count = 0
    
    def unban(self):
        self.is_banned = False
        self.banned_until = None
        self.ban_reason = ""
        self.consecutive_fail_count = 0
    
    def reset_stats(self):
        self.success_count = 0
        self.consecutive_fail_count = 0
        self.total_success = 0
        self.total_fail = 0
        self.is_banned = False
        self.banned_until = None
        self.ban_reason = ""


class Settings(BaseModel):
    api_endpoints: List[APIEndpoint] = []
    default_max_success_count: int = 10
    default_max_fail_count: int = 3
    ban_duration_hours: int = 24
    request_retry_count: int = 2
    request_retry_delay: float = 1.0
    enable_detailed_log: bool = True
    timeout: int = 300
    current_api_index: int = 0


def load_config() -> Settings:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'api_endpoints' in data:
                    data['api_endpoints'] = [APIEndpoint(**ep) for ep in data['api_endpoints']]
                return Settings(**data)
        except Exception as e:
            print(f"加载配置失败: {e}")
    return Settings()


def save_config(settings: Settings):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = settings.model_dump()
    data['api_endpoints'] = [ep.model_dump() for ep in settings.api_endpoints]
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_available_api() -> Optional[APIEndpoint]:
    config = load_config()
    if not config.api_endpoints:
        return None
    
    if config.current_api_index < len(config.api_endpoints):
        api = config.api_endpoints[config.current_api_index]
        if api.is_available():
            return api
    
    for i, api in enumerate(config.api_endpoints):
        if api.is_available():
            config.current_api_index = i
            save_config(config)
            return api
    
    # 重置未封禁的 API 额度
    for api in config.api_endpoints:
        if api.enabled and not api.is_banned:
            api.reset_quota()
    save_config(config)
    
    for i, api in enumerate(config.api_endpoints):
        if api.is_available():
            config.current_api_index = i
            save_config(config)
            return api
    
    return None


def get_current_api() -> Optional[APIEndpoint]:
    config = load_config()
    if not config.api_endpoints:
        return None
    if config.current_api_index < len(config.api_endpoints):
        return config.api_endpoints[config.current_api_index]
    return config.api_endpoints[0] if config.api_endpoints else None


def switch_to_api(api_id: str) -> bool:
    config = load_config()
    for i, api in enumerate(config.api_endpoints):
        if api.id == api_id:
            config.current_api_index = i
            save_config(config)
            return True
    return False


def update_api_status(api_id: str, success: bool):
    config = load_config()
    for i, api in enumerate(config.api_endpoints):
        if api.id == api_id:
            if success:
                api.record_success()
                if api.success_count >= api.max_success_count:
                    config.current_api_index = (i + 1) % len(config.api_endpoints)
            else:
                if api.record_fail(config.ban_duration_hours):
                    config.current_api_index = (i + 1) % len(config.api_endpoints)
            break
    save_config(config)