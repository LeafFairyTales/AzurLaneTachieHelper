import logging
import sys

# Windows 下统一 UTF-8 输出：避免 GBK 代码页/管道把 rich 日志（│ 等字符）渲染成乱码
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from rich.console import Console
from rich.logging import RichHandler
from rich.rule import Rule
from rich.style import Style
from rich.theme import Theme

# Add rich console logger
console = Console(
    theme=Theme(
        {
            "repr.str": Style(color="khaki1", bold=True),
            "repr.bool_true": Style(color="green", bold=False, italic=True),
            "repr.bool_false": Style(color="red", bold=False, italic=True),
        }
    )
)
console_fmt = logging.Formatter(fmt="%(asctime)s.%(msecs)03d │ %(message)s", datefmt=r"%m-%d %H:%M:%S")
console_hdlr = RichHandler(console=console, show_path=False, show_time=False)
console_hdlr.setFormatter(console_fmt)

# Logger init
logger_debug = False
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if logger_debug else logging.INFO)
logger.addHandler(console_hdlr)


def rule(title="", *, characters="─", style="rule.line", end="\n", align="center"):
    rule = Rule(title=title, characters=characters, style=style, end=end, align=align)
    console_hdlr.console.print(rule)


def hr(title, level=3):
    if level == 1:
        logger.rule(title, characters="═")
    if level == 2:
        logger.rule(title, characters="─")
    if level == 3:
        logger.info(f"[bold]{title}[/bold]", extra={"markup": True})
    if level == 0:
        logger.rule(characters="═")
        logger.rule(title, characters=" ")
        logger.rule(characters="═")


def attr(name, text):
    logger.info(f"[[bold]{name}[/bold]] {text}", extra={"markup": True})


def log_wrapper(func):
    def inner(msg, *args, **kwargs):
        extra = kwargs.get("extra", {})
        kwargs["extra"] = extra | {"markup": True, "emoji": True}
        return func(msg, *args, **kwargs)

    return inner


logger.hr = hr
logger.attr = attr
logger.rule = rule
logger.print = console_hdlr.console.print
logger.info = log_wrapper(logger.info)
logger.warning = log_wrapper(logger.warning)
logger.error = log_wrapper(logger.error)
