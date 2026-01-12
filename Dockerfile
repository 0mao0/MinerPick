# 使用 Python 3.10 基础镜像（支持新的类型注解语法）
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖（使用清华源加速）
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 复制项目文件
COPY backend/ ./backend/
COPY .env.example .env
COPY input/ ./input/
COPY output/ ./output/

# 创建必要的目录
RUN mkdir -p /app/input /app/output /app/backend/static

# 暴露端口
EXPOSE 8000

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 启动应用
CMD ["python", "backend/main.py"]
