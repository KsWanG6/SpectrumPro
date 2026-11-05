import sys, os, traceback


def _report(text):
    try:
        import tempfile
        path = os.path.join(os.environ.get("TEMP") or tempfile.gettempdir(), "SpectrumPro_error.log")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        if sys.platform != "win32":
            return
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, "SpectrumPro 發生錯誤，詳情見：\n" + path, "SpectrumPro", 0x10)
    except Exception:
        pass


try:
    from ramanproc.gui.app import main
    main()
except SystemExit:
    raise
except BaseException:
    _report(traceback.format_exc())
    raise
