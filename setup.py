from setuptools import setup, find_packages
import os

# Read requirements
with open('requirements.txt') as f:
    requirements = f.read().splitlines()

setup(
    name="minerpick",
    version="0.1.0",
    description="A full stack PDF-Markdown highlight and edit tool (including table-cells) designed for LLM use, based on cloud MinerU + local gmft.",
    author="0mao0",
    license="MIT",
    packages=find_packages(),
    include_package_data=True,
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "minerpick=backend.main:start",
        ],
    },
    python_requires=">=3.8",
)