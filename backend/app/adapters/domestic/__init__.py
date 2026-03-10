"""Domestic (Chinese) provider adapters."""

from app.adapters.domestic.aliyun import ALIYUN_MODELS, AliyunAdapter
from app.adapters.domestic.baidu import BAIDU_MODELS, BaiduAdapter
from app.adapters.domestic.zhipu import ZHIPU_MODELS, ZhipuAdapter
from app.adapters.domestic.deepseek import DEEPSEEK_MODELS, DeepSeekAdapter
from app.adapters.domestic.minimax import MINIMAX_MODELS, MiniMaxAdapter
from app.adapters.domestic.moonshot import MOONSHOT_MODELS, MoonshotAdapter
from app.adapters.domestic.baichuan import BAICHUAN_MODELS, BaichuanAdapter

__all__ = [
    "AliyunAdapter",
    "ALIYUN_MODELS",
    "BaiduAdapter",
    "BAIDU_MODELS",
    "ZhipuAdapter",
    "ZHIPU_MODELS",
    "DeepSeekAdapter",
    "DEEPSEEK_MODELS",
    "MiniMaxAdapter",
    "MINIMAX_MODELS",
    "MoonshotAdapter",
    "MOONSHOT_MODELS",
    "BaichuanAdapter",
    "BAICHUAN_MODELS",
]
