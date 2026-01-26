"""测试亲密度统一方案"""
import pytest
from app.services.affinity_service import AffinityService
from app.services.affinity_service_v2 import AffinityServiceV2


class TestAffinityNormalization:
    """测试分数归一化逻辑"""
    
    def test_normalize_score_01_range(self):
        """测试 0~1 范围的分数不变"""
        assert AffinityService._normalize_score(0.0) == 0.0
        assert AffinityService._normalize_score(0.5) == 0.5
        assert AffinityService._normalize_score(1.0) == 1.0
    
    def test_normalize_score_0_100_range(self):
        """测试 0~100 范围的分数转换为 0~1"""
        assert AffinityService._normalize_score(0.0) == 0.0
        assert AffinityService._normalize_score(50.0) == 0.5
        assert AffinityService._normalize_score(100.0) == 1.0
        assert AffinityService._normalize_score(150.0) == 1.0  # clamp
    
    def test_normalize_score_negative_range(self):
        """测试 -1~1 范围的分数转换为 0~1"""
        assert AffinityService._normalize_score(-1.0) == 0.0
        assert abs(AffinityService._normalize_score(-0.5) - 0.25) < 0.01
        # 注意：0.0 会被当作 0~1 范围，不会转换
    
    def test_legacy_to_01_conversion(self):
        """测试旧版 -1~1 到 0~1 的转换"""
        assert AffinityService._legacy_to_01(-1.0) == 0.0
        assert AffinityService._legacy_to_01(0.0) == 0.5
        assert AffinityService._legacy_to_01(1.0) == 1.0
    
    def test_01_to_legacy_conversion(self):
        """测试 0~1 到旧版 -1~1 的转换"""
        assert AffinityService._01_to_legacy(0.0) == -1.0
        assert AffinityService._01_to_legacy(0.5) == 0.0
        assert AffinityService._01_to_legacy(1.0) == 1.0


class TestAffinityV2Conversion:
    """测试 V2 双向尺度转换"""
    
    def test_score_01_to_100(self):
        """测试 0~1 到 0~100 的转换"""
        assert AffinityServiceV2._score_01_to_100(0.0) == 0.0
        assert AffinityServiceV2._score_01_to_100(0.5) == 50.0
        assert AffinityServiceV2._score_01_to_100(1.0) == 100.0
    
    def test_score_100_to_01(self):
        """测试 0~100 到 0~1 的转换"""
        assert AffinityServiceV2._score_100_to_01(0.0) == 0.0
        assert AffinityServiceV2._score_100_to_01(50.0) == 0.5
        assert AffinityServiceV2._score_100_to_01(100.0) == 1.0
        assert AffinityServiceV2._score_100_to_01(150.0) == 1.0  # clamp
    
    def test_roundtrip_conversion(self):
        """测试往返转换不丢失精度"""
        original = 0.75
        converted = AffinityServiceV2._score_01_to_100(original)
        back = AffinityServiceV2._score_100_to_01(converted)
        assert abs(original - back) < 0.01


class TestAffinityStateMapping:
    """测试状态映射"""
    
    def test_legacy_state_mapping(self):
        """测试旧版状态映射（0~1 尺度）"""
        assert AffinityService.calculate_state(0.0) == "stranger"
        assert AffinityService.calculate_state(0.1) == "stranger"
        assert AffinityService.calculate_state(0.3) == "acquaintance"
        assert AffinityService.calculate_state(0.5) == "friend"
        assert AffinityService.calculate_state(0.7) == "close_friend"
        assert AffinityService.calculate_state(0.9) == "best_friend"
    
    def test_v2_state_mapping(self):
        """测试 V2 状态映射（0~100 尺度）"""
        assert AffinityServiceV2.calculate_state(10) == "stranger"
        assert AffinityServiceV2.calculate_state(30) == "acquaintance"
        assert AffinityServiceV2.calculate_state(60) == "friend"
        assert AffinityServiceV2.calculate_state(90) == "close_friend"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
