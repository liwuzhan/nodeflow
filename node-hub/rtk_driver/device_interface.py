"""
RTK设备通信接口
支持串口、TCP、UDP连接
"""

import serial
import socket
import time
from typing import Optional, List
from abc import ABC, abstractmethod


class DeviceInterface(ABC):
    """设备通信接口基类"""

    @abstractmethod
    def connect(self) -> bool:
        """连接设备"""
        pass

    @abstractmethod
    def disconnect(self):
        """断开连接"""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """检查连接状态"""
        pass

    @abstractmethod
    def read_line(self, timeout: float = 1.0) -> Optional[str]:
        """读取一行数据"""
        pass

    @abstractmethod
    def write(self, data: str) -> bool:
        """写入数据"""
        pass


class SerialInterface(DeviceInterface):
    """串口通信接口"""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        """
        初始化串口接口

        Args:
            port: 串口设备路径（如 /dev/ttyUSB0, COM3）
            baudrate: 波特率
            timeout: 读取超时时间（秒）
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial: Optional[serial.Serial] = None
        self.buffer = b""

    def connect(self) -> bool:
        """打开串口连接"""
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False
            )

            # 清空缓冲区
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
            self.buffer = b""

            return True

        except serial.SerialException as e:
            return False

    def disconnect(self):
        """关闭串口"""
        if self.serial and self.serial.is_open:
            try:
                self.serial.close()
            except:
                pass
        self.serial = None
        self.buffer = b""

    def is_connected(self) -> bool:
        """检查串口是否打开"""
        return self.serial is not None and self.serial.is_open

    def read_line(self, timeout: float = 1.0) -> Optional[str]:
        """
        读取一行NMEA数据（以\r\n结尾）

        Args:
            timeout: 超时时间（秒）

        Returns:
            一行字符串数据，失败返回None
        """
        if not self.is_connected():
            return None

        start_time = time.time()

        try:
            while time.time() - start_time < timeout:
                # 读取可用数据
                if self.serial.in_waiting > 0:
                    chunk = self.serial.read(self.serial.in_waiting)
                    self.buffer += chunk

                # 检查是否有完整的行
                if b'\n' in self.buffer:
                    line, self.buffer = self.buffer.split(b'\n', 1)
                    # 解码并返回（去除\r）
                    return line.decode('ascii', errors='ignore').strip()

                # 短暂休眠避免CPU占用
                time.sleep(0.001)

            return None

        except (serial.SerialException, UnicodeDecodeError):
            return None

    def write(self, data: str) -> bool:
        """
        写入数据到串口

        Args:
            data: 要写入的字符串

        Returns:
            成功返回True
        """
        if not self.is_connected():
            return False

        try:
            # 确保数据以\r\n结尾
            if not data.endswith('\r\n'):
                data = data + '\r\n'

            self.serial.write(data.encode('ascii'))
            return True

        except serial.SerialException:
            return False

    def send_command(self, command: str) -> bool:
        """
        发送命令到RTK设备

        Args:
            command: 命令字符串（如 "GPGSV 1", "KSXT COM2 20"）

        Returns:
            成功返回True
        """
        # RTK命令格式通常不需要$前缀和校验和
        return self.write(command)


class TCPInterface(DeviceInterface):
    """TCP网络通信接口"""

    def __init__(self, host: str, port: int, timeout: float = 1.0):
        """
        初始化TCP接口

        Args:
            host: 设备IP地址
            port: 端口号
            timeout: 超时时间
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.socket: Optional[socket.socket] = None
        self.buffer = b""

    def connect(self) -> bool:
        """建立TCP连接"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.timeout)
            self.socket.connect((self.host, self.port))
            self.buffer = b""
            return True

        except (socket.error, socket.timeout):
            return False

    def disconnect(self):
        """关闭TCP连接"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        self.socket = None
        self.buffer = b""

    def is_connected(self) -> bool:
        """检查TCP连接状态"""
        return self.socket is not None

    def read_line(self, timeout: float = 1.0) -> Optional[str]:
        """读取一行数据"""
        if not self.is_connected():
            return None

        start_time = time.time()
        self.socket.settimeout(0.1)  # 设置短超时以便循环检查

        try:
            while time.time() - start_time < timeout:
                # 尝试接收数据
                try:
                    chunk = self.socket.recv(4096)
                    if not chunk:
                        # 连接关闭
                        return None
                    self.buffer += chunk
                except socket.timeout:
                    pass

                # 检查完整行
                if b'\n' in self.buffer:
                    line, self.buffer = self.buffer.split(b'\n', 1)
                    return line.decode('ascii', errors='ignore').strip()

                time.sleep(0.001)

            return None

        except (socket.error, UnicodeDecodeError):
            return None

    def write(self, data: str) -> bool:
        """写入数据"""
        if not self.is_connected():
            return False

        try:
            if not data.endswith('\r\n'):
                data = data + '\r\n'

            self.socket.sendall(data.encode('ascii'))
            return True

        except socket.error:
            return False


class UDPInterface(DeviceInterface):
    """UDP网络通信接口"""

    def __init__(self, host: str, port: int, timeout: float = 1.0):
        """
        初始化UDP接口

        Args:
            host: 设备IP地址
            port: 端口号
            timeout: 超时时间
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.socket: Optional[socket.socket] = None

    def connect(self) -> bool:
        """创建UDP socket"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.settimeout(self.timeout)
            return True

        except socket.error:
            return False

    def disconnect(self):
        """关闭UDP socket"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        self.socket = None

    def is_connected(self) -> bool:
        """检查UDP socket状态"""
        return self.socket is not None

    def read_line(self, timeout: float = 1.0) -> Optional[str]:
        """接收UDP数据包"""
        if not self.is_connected():
            return None

        self.socket.settimeout(timeout)

        try:
            data, addr = self.socket.recvfrom(4096)
            # UDP每个包通常包含完整NMEA语句
            return data.decode('ascii', errors='ignore').strip()

        except (socket.timeout, socket.error, UnicodeDecodeError):
            return None

    def write(self, data: str) -> bool:
        """发送UDP数据包"""
        if not self.is_connected():
            return False

        try:
            if not data.endswith('\r\n'):
                data = data + '\r\n'

            self.socket.sendto(data.encode('ascii'), (self.host, self.port))
            return True

        except socket.error:
            return False


def create_interface(config: dict) -> DeviceInterface:
    """
    根据配置创建设备接口

    Args:
        config: 配置字典，包含连接参数

    Returns:
        DeviceInterface实例
    """
    use_network = config.get('use_network', False)

    if use_network:
        protocol = config.get('network_protocol', 'tcp').lower()
        host = config.get('network_host', '192.168.1.100')
        port = config.get('network_port', 5000)
        timeout = config.get('serial_timeout', 1.0)

        if protocol == 'tcp':
            return TCPInterface(host, port, timeout)
        elif protocol == 'udp':
            return UDPInterface(host, port, timeout)
        else:
            raise ValueError(f"Unsupported network protocol: {protocol}")

    else:
        # 串口模式
        port = config.get('serial_port', '/dev/ttyUSB0')
        baudrate = config.get('serial_baudrate', 115200)
        timeout = config.get('serial_timeout', 1.0)

        return SerialInterface(port, baudrate, timeout)
