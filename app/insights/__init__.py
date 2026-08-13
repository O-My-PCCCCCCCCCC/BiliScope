"""行为洞察后端包：每个分析维度一个独立模块。"""
from app.insights.interest import interest_drift

__all__ = ["interest_drift"]
