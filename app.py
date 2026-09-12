"""海克斯大乱斗助手入口。"""
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="海克斯大乱斗助手")
    parser.add_argument("--self-test", metavar="REPORT", help="离线检查打包资源，写入 JSON 报告")
    parser.add_argument("--self-test-image", metavar="IMAGE", help="自检时额外识别指定选英雄截图")
    args = parser.parse_args()
    if args.self_test:
        from hexassist.diagnostics import run
        raise SystemExit(run(args.self_test, args.self_test_image))
    from hexassist.gui import main
    main()
