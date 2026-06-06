@echo off
conda create -y -n campus-scheduler python=3.12
conda run -n campus-scheduler python -m pip install -r d:\project\chengshedazuoye\requirements.txt --no-input
