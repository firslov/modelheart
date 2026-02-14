"""熔断器模式实现

防止级联失败，提供故障隔离和自动恢复机制。

工作原理：
1. CLOSED 状态：正常状态，所有请求正常转发
2. 当连续失败次数达到阈值时，进入 OPEN 状态
3. OPEN 状态：快速失败，所有请求立即返回错误，不再转发
4. 经过 recovery_timeout 后，进入 HALF_OPEN 状态
5. HALF_OPEN 状态：允许少量试探请求通过
   - 如果成功，恢复正常 (CLOSED)
   - 如果失败，重新熔断 (OPEN)
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional
import time

from app.utils.logging_config import get_logger

logger = get_logger(__name__)


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"           # 正常状态，允许请求通过
    OPEN = "open"               # 熔断状态，快速失败
    HALF_OPEN = "half_open"     # 半开状态，试探性请求


@dataclass
class CircuitStats:
    """单个熔断器的统计信息"""
    failures: int = 0                    # 连续失败次数
    successes: int = 0                   # 半开状态下的成功次数
    last_failure_time: float = 0         # 最后一次失败的时间戳
    state: CircuitState = CircuitState.CLOSED
    total_requests: int = 0              # 总请求数（用于监控）
    total_failures: int = 0              # 总失败数（用于监控）
    total_circuit_opens: int = 0         # 熔断次数（用于监控）
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def to_dict(self) -> dict:
        """导出为字典（用于监控和调试）"""
        return {
            "state": self.state.value,
            "failures": self.failures,
            "successes": self.successes,
            "last_failure_time": self.last_failure_time,
            "total_requests": self.total_requests,
            "total_failures": self.total_failures,
            "total_circuit_opens": self.total_circuit_opens,
        }


class CircuitBreaker:
    """熔断器实现

    使用示例：
        circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=30.0,
            half_open_max_calls=3,
        )

        # 检查是否允许请求
        if await circuit_breaker.can_execute("server_1"):
            try:
                result = await make_request()
                await circuit_breaker.record_success("server_1")
            except Exception:
                await circuit_breaker.record_failure("server_1")

    配置参数说明：
        failure_threshold: 连续失败多少次后触发熔断（默认 5 次）
        recovery_timeout: 熔断后等待多长时间尝试恢复（默认 30 秒）
        half_open_max_calls: 半开状态下允许的最大试探请求数（默认 3 个）
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
    ):
        """初始化熔断器

        Args:
            failure_threshold: 连续失败次数阈值，达到后触发熔断
            recovery_timeout: 熔断后恢复尝试的等待时间（秒）
            half_open_max_calls: 半开状态最大试探请求数
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self._circuits: Dict[str, CircuitStats] = {}
        self._stats_lock = asyncio.Lock()

        logger.info(
            f"CircuitBreaker initialized | "
            f"failure_threshold={failure_threshold} | "
            f"recovery_timeout={recovery_timeout}s | "
            f"half_open_max_calls={half_open_max_calls}"
        )

    def _get_circuit(self, key: str) -> CircuitStats:
        """获取或创建熔断器实例"""
        if key not in self._circuits:
            self._circuits[key] = CircuitStats()
        return self._circuits[key]

    async def can_execute(self, key: str) -> bool:
        """检查是否允许执行请求

        Args:
            key: 熔断器标识（通常是服务器 URL 或名称）

        Returns:
            bool: True 表示允许执行，False 表示应该快速失败
        """
        circuit = self._get_circuit(key)

        async with circuit.lock:
            current_time = time.time()
            circuit.total_requests += 1

            if circuit.state == CircuitState.CLOSED:
                # 正常状态，允许请求
                return True

            elif circuit.state == CircuitState.OPEN:
                # 熔断状态，检查是否可以尝试恢复
                time_since_failure = current_time - circuit.last_failure_time

                if time_since_failure >= self.recovery_timeout:
                    # 超过恢复时间，进入半开状态
                    old_state = circuit.state
                    circuit.state = CircuitState.HALF_OPEN
                    circuit.failures = 0
                    circuit.successes = 0

                    logger.info(
                        f"Circuit state change | key={key} | "
                        f"{old_state.value} -> {circuit.state.value} | "
                        f"recovery_after={time_since_failure:.1f}s"
                    )
                    return True

                # 仍在熔断期内，快速失败
                remaining = self.recovery_timeout - time_since_failure
                logger.debug(
                    f"Circuit OPEN | key={key} | remaining={remaining:.1f}s"
                )
                return False

            elif circuit.state == CircuitState.HALF_OPEN:
                # 半开状态，限制并发请求数
                if circuit.successes < self.half_open_max_calls:
                    return True

                # 已达到半开状态的最大请求数，拒绝新请求
                logger.debug(
                    f"Circuit HALF_OPEN max calls reached | key={key} | "
                    f"successes={circuit.successes}"
                )
                return False

        return True

    async def record_success(self, key: str):
        """记录成功请求

        在请求成功后调用，用于恢复正常状态。

        Args:
            key: 熔断器标识
        """
        circuit = self._get_circuit(key)

        async with circuit.lock:
            circuit.failures = 0  # 重置连续失败计数

            if circuit.state == CircuitState.HALF_OPEN:
                circuit.successes += 1

                if circuit.successes >= self.half_open_max_calls:
                    # 半开状态下连续成功，恢复正常
                    old_state = circuit.state
                    circuit.state = CircuitState.CLOSED
                    circuit.successes = 0

                    logger.info(
                        f"Circuit RECOVERED | key={key} | "
                        f"{old_state.value} -> {circuit.state.value}"
                    )
            elif circuit.state == CircuitState.CLOSED:
                # 正常状态下的成功，无需特殊处理
                pass

    async def record_failure(self, key: str, error: Optional[Exception] = None):
        """记录失败请求

        在请求失败后调用，可能触发熔断。

        Args:
            key: 熔断器标识
            error: 可选的异常信息，用于日志记录
        """
        circuit = self._get_circuit(key)

        async with circuit.lock:
            circuit.failures += 1
            circuit.total_failures += 1
            circuit.last_failure_time = time.time()

            if circuit.state == CircuitState.HALF_OPEN:
                # 半开状态下任何失败都重新熔断
                circuit.state = CircuitState.OPEN
                circuit.total_circuit_opens += 1
                circuit.successes = 0

                logger.warning(
                    f"Circuit RE-OPENED from half-open | key={key} | "
                    f"error={str(error) if error else 'unknown'}"
                )

            elif circuit.state == CircuitState.CLOSED:
                # 正常状态，检查是否达到熔断阈值
                if circuit.failures >= self.failure_threshold:
                    circuit.state = CircuitState.OPEN
                    circuit.total_circuit_opens += 1

                    logger.warning(
                        f"Circuit OPENED | key={key} | "
                        f"failures={circuit.failures}/{self.failure_threshold} | "
                        f"error={str(error) if error else 'unknown'}"
                    )

    def get_state(self, key: str) -> CircuitState:
        """获取指定熔断器的当前状态（非线程安全，仅用于监控）"""
        circuit = self._get_circuit(key)
        return circuit.state

    def get_all_stats(self) -> Dict[str, dict]:
        """获取所有熔断器的统计信息（用于监控）"""
        return {
            key: circuit.to_dict()
            for key, circuit in self._circuits.items()
        }

    def get_config(self) -> dict:
        """获取熔断器配置"""
        return {
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "half_open_max_calls": self.half_open_max_calls,
        }

    async def reset(self, key: str):
        """手动重置指定熔断器（用于运维操作）"""
        circuit = self._get_circuit(key)

        async with circuit.lock:
            old_state = circuit.state
            circuit.state = CircuitState.CLOSED
            circuit.failures = 0
            circuit.successes = 0

            logger.info(
                f"Circuit RESET manually | key={key} | "
                f"{old_state.value} -> {circuit.state.value}"
            )

    async def reset_all(self):
        """重置所有熔断器"""
        for key in list(self._circuits.keys()):
            await self.reset(key)

        logger.info("All circuits reset")
