"""Compatibility adapter for the AI CLI; rendering is in ui.py."""


def select_items(items, label):
    from ui import TerminalUI
    return TerminalUI().select("选择任务", items, label)


def run_ai_menu(version, login):
    from app import Application
    from ui import TerminalUI, Cancelled
    view = TerminalUI()
    with view.session():
        try:
            return Application(view).ai(version, login)
        except (Cancelled, KeyboardInterrupt, EOFError):
            view.cancelled = True
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("AI 运行失败")
            view.pending_error = str(exc)
        finally:
            view.finish()
