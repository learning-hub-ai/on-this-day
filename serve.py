#!/usr/bin/env python3
"""
serve.py — 本地预览服务器

为什么需要它：本项目用 `fetch()` 读 `data/otd/*.json`，而现代浏览器
在 `file://` 下按同源策略拦截 fetch，ES module 的 import 同样被拦。
所以**不能双击 index.html 打开**，必须经由 HTTP。
（hanzi-go 也有 server.py，同一原因。）

用法：
    python3 serve.py            # http://127.0.0.1:8000
    python3 serve.py 8080       # 指定端口

无依赖，只用标准库。生产部署不需要它 —— GitHub Pages 本身就是 HTTP。
"""

import http.server
import os
import socketserver
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
ROOT = os.path.dirname(os.path.abspath(__file__))


class Handler(http.server.SimpleHTTPRequestHandler):
    """静态文件服务，额外做两件事：正确的 JSON MIME ＋ 禁用缓存。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def end_headers(self):
        # 开发时禁用缓存，否则改了 JSON 还看到旧数据
        self.send_header('Cache-Control', 'no-store, must-revalidate')
        super().end_headers()

    def log_message(self, fmt, *args):
        # 只记非 200，避免刷屏
        if args and not str(args[1]).startswith('2'):
            super().log_message(fmt, *args)


if __name__ == '__main__':
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(('127.0.0.1', PORT), Handler) as httpd:
        print(f'历史上的今天 → http://127.0.0.1:{PORT}')
        print('Ctrl+C 停止')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\n已停止')
