from setuptools import setup

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="py3dmol",
    version="2.0.1",
    author="3dmol",
    description="An interface to 3Dmol.js with enhanced image capture capabilities",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/avirshup/py3dmol",
    packages=['py3dmol'],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7',
    install_requires=[
        'ipython>=7.0.0',
        'ipywidgets>=7.0.0',
        'fastapi>=0.104.0',
        'uvicorn>=0.24.0',
        'pillow>=10.0.0',
        'numpy>=1.24.0',
        'python-multipart>=0.0.6',
        'requests>=2.31.0',
        'pydantic>=2.0.0',
        'selenium>=4.15.0',
        'webdriver-manager>=4.0.0',
    ],
)
