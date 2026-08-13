"""行为洞察后端包：每个分析维度一个独立模块。"""
from app.insights.interest import interest_drift
from app.insights.cross_time import time_content_cross
from app.insights.time_invest import time_invest

__all__ = ["interest_drift", "time_content_cross", "time_invest"]
