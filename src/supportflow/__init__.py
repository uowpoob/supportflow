def main() -> None:
    """Start the local development API."""
    import uvicorn

    # loop 必须指定成 Selector：连 Postgres 用的 psycopg 跑不了 Windows 默认的
    # ProactorEventLoop。uvicorn 是自己造事件循环的（它显式传了 loop_factory），
    # 所以脚本里那套 set_event_loop_policy 在 uvicorn 下无效，只能从这里传。
    # 在 Linux / macOS 上它本来就是默认值，写出来无害。
    uvicorn.run(
        "supportflow.main:app",
        host="127.0.0.1",
        port=8080,
        loop="asyncio:SelectorEventLoop",
    )
