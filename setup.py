from setuptools import setup, find_packages

setup(
    name="melodine",
    version="1.0.0",
    description="Interactive music downloader with beautiful TUI",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="KROFN",
    url="https://github.com/KROFN/melodine",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "yt-dlp>=2024.0.0",
        "rich>=13.0.0",
        "InquirerPy>=0.3.4",
        "mutagen>=1.47.0",
        "pyyaml>=6.0",
        "pydantic>=2.0.0",
    ],
    entry_points={
        "console_scripts": [
            "melodine=main:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Environment :: Console",
        "Topic :: Multimedia :: Sound/Audio",
    ],
)