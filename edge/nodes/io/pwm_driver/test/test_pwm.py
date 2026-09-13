#!/usr/bin/env python3
"""
PWM Driver 单元测试

测试内容：
1. PWM 值到纳秒的映射 (_pwm_to_ns)
2. 运动学计算 (atom.py)
3. PWM 控制器整体逻辑
"""

import sys
import os
from pathlib import Path

# 添加 atom.py 路径
test_dir = Path(__file__).parent
atom_path = test_dir.parent
sys.path.insert(0, str(atom_path))

import pytest
import time
from unittest.mock import Mock, patch, MagicMock, mock_open


# ========== 导入被测模块 ==========
from edge.nodes.io.pwm_driver import atom


# ========== 测试数据常量 ==========
class TestConstants:
    """测试常量"""
    WHEEL_BASE = 0.5  # m
    MAX_LINEAR_SPEED = 2.0  # m/s
    MAX_ANGULAR_SPEED = 1.0  # rad/s
    PWM_RANGE = 1024
    NEUTRAL_PWM = 512
    MAX_PWM_DELTA = 400
    MIN_PWM_THRESHOLD = 50

    # RC PWM 常量
    PWM_PERIOD_NS = 20000000  # 20ms (50Hz)
    PWM_CENTER_NS = 1500000   # 1.5ms
    PWM_MIN_NS = 1000000      # 1ms
    PWM_MAX_NS = 2000000      # 2ms


# ========== 测试差速运动学 ==========
class TestDifferentialDriveKinematics:
    """测试双轮差速运动学计算"""

    @pytest.fixture
    def kinematics(self):
        """创建运动学实例"""
        return atom.DifferentialDriveKinematics(
            wheel_base=TestConstants.WHEEL_BASE,
            max_linear_speed=TestConstants.MAX_LINEAR_SPEED,
            max_angular_speed=TestConstants.MAX_ANGULAR_SPEED
        )

    def test_straight_line(self, kinematics):
        """测试直线运动"""
        v_linear = 1.0  # m/s
        w_angular = 0.0  # rad/s

        v_left, v_right = kinematics.velocity_to_wheel_speeds(v_linear, w_angular)

        assert v_left == pytest.approx(1.0)
        assert v_right == pytest.approx(1.0)

    def test_pivot_turn_left(self, kinematics):
        """测试原地左转"""
        v_linear = 0.0
        w_angular = 1.0  # rad/s

        v_left, v_right = kinematics.velocity_to_wheel_speeds(v_linear, w_angular)

        # v_left = 0 - (0.5/2) * 1.0 = -0.25
        # v_right = 0 + (0.5/2) * 1.0 = 0.25
        assert v_left == pytest.approx(-0.25)
        assert v_right == pytest.approx(0.25)

    def test_pivot_turn_right(self, kinematics):
        """测试原地右转"""
        v_linear = 0.0
        w_angular = -1.0  # rad/s

        v_left, v_right = kinematics.velocity_to_wheel_speeds(v_linear, w_angular)

        assert v_left == pytest.approx(0.25)
        assert v_right == pytest.approx(-0.25)

    def test_forward_left_turn(self, kinematics):
        """测试前进左转"""
        v_linear = 1.0
        w_angular = 1.0

        v_left, v_right = kinematics.velocity_to_wheel_speeds(v_linear, w_angular)

        # v_left = 1.0 - 0.25 = 0.75
        # v_right = 1.0 + 0.25 = 1.25
        assert v_left == pytest.approx(0.75)
        assert v_right == pytest.approx(1.25)

    def test_reverse_kinematics(self, kinematics):
        """测试反向运动学（轮速→速度）"""
        v_left = 0.75
        v_right = 1.25

        v_linear, w_angular = kinematics.wheel_speeds_to_velocity(v_left, v_right)

        assert v_linear == pytest.approx(1.0)
        assert w_angular == pytest.approx(1.0)


# ========== 测试 PWM 映射 ==========
class TestPWMMapper:
    """测试 PWM 映射器"""

    @pytest.fixture
    def mapper(self):
        """创建 PWM 映射器实例"""
        return atom.PWMMapper(
            pwm_range=TestConstants.PWM_RANGE,
            neutral_pwm=TestConstants.NEUTRAL_PWM,
            max_pwm_delta=TestConstants.MAX_PWM_DELTA,
            min_pwm_threshold=TestConstants.MIN_PWM_THRESHOLD
        )

    def test_neutral_speed(self, mapper):
        """测试零速映射到中位 PWM"""
        pwm = mapper.speed_to_pwm(0.0, TestConstants.MAX_LINEAR_SPEED)
        assert pwm == TestConstants.NEUTRAL_PWM

    def test_forward_max_speed(self, mapper):
        """测试最大前进速度"""
        pwm = mapper.speed_to_pwm(TestConstants.MAX_LINEAR_SPEED, TestConstants.MAX_LINEAR_SPEED)
        expected = TestConstants.NEUTRAL_PWM + TestConstants.MAX_PWM_DELTA
        assert pwm == expected

    def test_backward_max_speed(self, mapper):
        """测试最大后退速度"""
        pwm = mapper.speed_to_pwm(-TestConstants.MAX_LINEAR_SPEED, TestConstants.MAX_LINEAR_SPEED)
        expected = TestConstants.NEUTRAL_PWM - TestConstants.MAX_PWM_DELTA
        assert pwm == expected

    def test_half_speed_forward(self, mapper):
        """测试半速前进"""
        pwm = mapper.speed_to_pwm(1.0, TestConstants.MAX_LINEAR_SPEED)
        # 512 + (1.0/2.0) * 400 = 712
        expected = TestConstants.NEUTRAL_PWM + int(TestConstants.MAX_PWM_DELTA * 0.5)
        assert pwm == expected

    def test_dead_zone(self, mapper):
        """测试死区处理"""
        # 低于阈值的速度应该映射到中位
        small_speed = 0.05  # 很小的速度
        max_speed = 2.0
        pwm = mapper.speed_to_pwm(small_speed, max_speed)

        # 计算预期的 PWM 偏移
        offset = int((small_speed / max_speed) * TestConstants.MAX_PWM_DELTA)
        if offset < TestConstants.MIN_PWM_THRESHOLD:
            expected_pwm = TestConstants.NEUTRAL_PWM
        else:
            expected_pwm = TestConstants.NEUTRAL_PWM + offset

        assert pwm == expected_pwm

    def test_speed_clamping(self, mapper):
        """测试速度超限时的限制"""
        # 超过最大速度应该被限制
        pwm = mapper.speed_to_pwm(5.0, TestConstants.MAX_LINEAR_SPEED)
        expected = TestConstants.NEUTRAL_PWM + TestConstants.MAX_PWM_DELTA
        assert pwm == expected

    def test_pwm_to_speed_reverse(self, mapper):
        """测试 PWM 到速度的反向映射"""
        # 中位 PWM → 0 速度
        speed = mapper.pwm_to_speed(TestConstants.NEUTRAL_PWM, TestConstants.MAX_LINEAR_SPEED)
        assert speed == 0.0

        # 最大 PWM → 最大速度
        speed = mapper.pwm_to_speed(
            TestConstants.NEUTRAL_PWM + TestConstants.MAX_PWM_DELTA,
            TestConstants.MAX_LINEAR_SPEED
        )
        assert speed == pytest.approx(TestConstants.MAX_LINEAR_SPEED)


# ========== 测试 PWM 控制器 ==========
class TestPWMController:
    """测试 PWM 控制器"""

    @pytest.fixture
    def controller(self):
        """创建 PWM 控制器实例"""
        return atom.PWMController(
            wheel_base=TestConstants.WHEEL_BASE,
            max_linear_speed=TestConstants.MAX_LINEAR_SPEED,
            max_angular_speed=TestConstants.MAX_ANGULAR_SPEED,
            pwm_range=TestConstants.PWM_RANGE,
            neutral_pwm=TestConstants.NEUTRAL_PWM,
            max_pwm_delta=TestConstants.MAX_PWM_DELTA,
            min_pwm_threshold=TestConstants.MIN_PWM_THRESHOLD,
            enable_safety_check=True
        )

    def test_neutral_command(self, controller):
        """测试中位命令（停止）"""
        cmd = atom.VelocityCommand(
            linear_velocity=0.0,
            angular_velocity=0.0,
            timestamp=time.time()
        )

        pwm_cmd = controller.calculate_pwm(cmd)

        assert pwm_cmd.left_pwm == TestConstants.NEUTRAL_PWM
        assert pwm_cmd.right_pwm == TestConstants.NEUTRAL_PWM

    def test_forward_command(self, controller):
        """测试前进命令"""
        cmd = atom.VelocityCommand(
            linear_velocity=1.0,
            angular_velocity=0.0,
            timestamp=time.time()
        )

        pwm_cmd = controller.calculate_pwm(cmd)

        # 左右轮应该相同
        assert pwm_cmd.left_pwm == pwm_cmd.right_pwm
        # 应该大于中位
        assert pwm_cmd.left_pwm > TestConstants.NEUTRAL_PWM

    def test_turn_left_command(self, controller):
        """测试左转命令"""
        cmd = atom.VelocityCommand(
            linear_velocity=0.0,
            angular_velocity=1.0,  # 逆时针
            timestamp=time.time()
        )

        pwm_cmd = controller.calculate_pwm(cmd)

        # 左轮后退（PWM < 中位），右轮前进（PWM > 中位）
        assert pwm_cmd.left_pwm < TestConstants.NEUTRAL_PWM
        assert pwm_cmd.right_pwm > TestConstants.NEUTRAL_PWM

    def test_emergency_stop(self, controller):
        """测试紧急停止"""
        cmd = atom.VelocityCommand(
            linear_velocity=1.0,
            angular_velocity=0.5,
            timestamp=time.time()
        )

        pwm_cmd = controller.calculate_pwm(cmd, emergency_stop=True)

        assert pwm_cmd.left_pwm == TestConstants.NEUTRAL_PWM
        assert pwm_cmd.right_pwm == TestConstants.NEUTRAL_PWM
        assert pwm_cmd.linear_velocity == 0.0
        assert pwm_cmd.angular_velocity == 0.0

    def test_safety_check_clamping(self, controller):
        """测试安全检查（速度限制）"""
        # 超过最大速度的命令
        cmd = atom.VelocityCommand(
            linear_velocity=10.0,  # 远超最大速度
            angular_velocity=5.0,
            timestamp=time.time()
        )

        pwm_cmd = controller.calculate_pwm(cmd)

        # 反推的速度应该被限制在最大值内
        assert abs(pwm_cmd.linear_velocity) <= TestConstants.MAX_LINEAR_SPEED
        assert abs(pwm_cmd.angular_velocity) <= TestConstants.MAX_ANGULAR_SPEED

    def test_get_status(self, controller):
        """测试获取控制器状态"""
        status = controller.get_status()

        assert status['wheel_base'] == TestConstants.WHEEL_BASE
        assert status['max_linear_speed'] == TestConstants.MAX_LINEAR_SPEED
        assert status['max_angular_speed'] == TestConstants.MAX_ANGULAR_SPEED
        assert status['neutral_pwm'] == TestConstants.NEUTRAL_PWM
        assert status['safety_check_enabled'] is True


# ========== 测试 _pwm_to_ns 映射函数 ==========
class TestPWMToNS:
    """测试 PWM 值到纳秒的映射 (run.py 中的 _pwm_to_ns 逻辑)"""

    def pwm_to_ns(self, pwm_value: int,
                  neutral_pwm: int = TestConstants.NEUTRAL_PWM,
                  max_pwm_delta: int = TestConstants.MAX_PWM_DELTA,
                  center_ns: int = TestConstants.PWM_CENTER_NS) -> int:
        """模拟 run.py 中的 _pwm_to_ns 方法"""
        offset = pwm_value - neutral_pwm
        ratio = offset / max_pwm_delta
        ratio = max(-1.0, min(1.0, ratio))

        # delta_ns = (max_pwm_delta / neutral_pwm) * center_ns
        pwm_delta_ratio = max_pwm_delta / neutral_pwm
        delta_ns = int(pwm_delta_ratio * center_ns)

        ns = center_ns + int(ratio * delta_ns)

        # 限制在 RC 有效范围
        ns = max(1000000, min(2000000, ns))
        return ns

    def test_neutral_pwm_to_ns(self):
        """测试中位 PWM 映射到 1.5ms"""
        ns = self.pwm_to_ns(TestConstants.NEUTRAL_PWM)
        assert ns == TestConstants.PWM_CENTER_NS  # 1.5ms

    def test_max_forward_pwm_to_ns(self):
        """测试最大前进 PWM"""
        ns = self.pwm_to_ns(TestConstants.NEUTRAL_PWM + TestConstants.MAX_PWM_DELTA)
        # 应该接近 2ms (但不超过)
        assert ns <= 2000000
        assert ns > 1500000

    def test_max_backward_pwm_to_ns(self):
        """测试最大后退 PWM"""
        ns = self.pwm_to_ns(TestConstants.NEUTRAL_PWM - TestConstants.MAX_PWM_DELTA)
        # 应该接近 1ms (但不低于)
        assert ns >= 1000000
        assert ns < 1500000

    def test_pwm_clamping(self):
        """测试 PWM 超出范围时的限制"""
        # 超大 PWM 值应该被限制到 2ms
        ns = self.pwm_to_ns(2000)
        assert ns == 2000000

        # 超小 PWM 值应该被限制到 1ms
        ns = self.pwm_to_ns(-100)
        assert ns == 1000000

    def test_rc_pwm_range(self):
        """测试所有 PWM 值都在 RC 有效范围内"""
        for pwm in range(0, 1024):
            ns = self.pwm_to_ns(pwm)
            assert 1000000 <= ns <= 2000000, f"PWM {pwm} → {ns} ns 超出范围"


# ========== 集成测试 ==========
class TestPWMIntegration:
    """PWM 控制器集成测试"""

    @pytest.fixture
    def controller(self):
        return atom.PWMController(
            wheel_base=0.5,
            max_linear_speed=2.0,
            max_angular_speed=1.0,
            pwm_range=1024,
            neutral_pwm=512,
            max_pwm_delta=400,
            min_pwm_threshold=50,
            enable_safety_check=True
        )

    def test_forward_turn_right_scenario(self, controller):
        """测试前进右转场景"""
        cmd = atom.VelocityCommand(
            linear_velocity=1.0,
            angular_velocity=-0.5,  # 右转
            timestamp=time.time()
        )

        pwm_cmd = controller.calculate_pwm(cmd)

        # 右转时，右轮速度应该小于左轮
        # 右轮 PWM 应该 < 左轮 PWM
        assert pwm_cmd.right_pwm < pwm_cmd.left_pwm
        # 两者都应该 > 中位（前进）
        assert pwm_cmd.left_pwm > 512
        assert pwm_cmd.right_pwm > 512

    def test_backward_turn_left_scenario(self, controller):
        """测试后退左转场景"""
        cmd = atom.VelocityCommand(
            linear_velocity=-0.5,
            angular_velocity=0.5,  # 左转
            timestamp=time.time()
        )

        pwm_cmd = controller.calculate_pwm(cmd)

        # 后退时，两者都应该 < 中位
        assert pwm_cmd.left_pwm < 512
        assert pwm_cmd.right_pwm < 512


# ========== 运行测试 ==========
if __name__ == "__main__":
    # 直接运行此文件执行测试
    pytest.main([__file__, "-v", "--tb=short"])
