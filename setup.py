from setuptools import setup, find_packages

setup(
    name="robot-nodeflow",
    version="0.1.0",
    description="机器人节点化框架 - 配置驱动的节点编排系统",
    author="Your Name",
    author_email="your.email@example.com",
    packages=find_packages(),
    install_requires=[
        "PyYAML>=6.0",
        "pyzmq>=24.0.0",
        "msgpack>=1.0.0",
        "pydantic>=2.0",
        "psutil>=5.8.0",
    ],
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "nodeflow=runtime.main:main",
            "nodeflow-cli=tools.cli.core.cli:main",
        ],
    },
)
