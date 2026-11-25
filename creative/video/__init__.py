"""
creative/video/ — 商品主图视频（图片 → 1:1 短视频）

images.py   找商品图片（品牌 IMAGE_PROCESS 目录，{商品编码}__{序号}.jpg）
render.py   渲染：缓慢推近 + 淡入淡出 + 中文字幕，ffmpeg 编码 H.264 MP4
service.py  批量：取文案（creative/copywriting）→ 渲染 → 视频清单 Excel

参数在 cfg/creative_config.py 的 VIDEO_* ；运行入口 ops/creative/run_generate_video.py
"""
