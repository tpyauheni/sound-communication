from os import stat
import sys
import time
import os.path as opath
from datetime import datetime
import traceback
import pyggwave


class Logger:
    TAG_NAMES: dict[str, str] = {
        '*E3': 'Third-party error',
        '*E3p': 'PyAudio error',
        '*E3g': 'GGWave error',
        '*E1': 'Error',
        '*W': 'Warning',
        '*I': 'Info',
        '*V': 'Verbose',
        '*Vb': 'Verbose (audio)',
        '*Vc': 'Verbose (coder)',
        '*Vf': 'Verbose (frame)',
        '*Vs': 'Verbose (stream)',
        '*Vg': 'Verbose (GGWave)',
        '*Vw': 'Verbose (warning)',
        '*O': 'OK',
        '*D': 'Debug',
        'f': 'File-only (slow)',
        'S': 'Spam',
        '': 'Unknown ({0})',
    }
    RESET_COLOR: str = '\x1b[0m'
    COLORS: dict[str, str] = {
        '*E': '\x1b[31m',
        '*E1': '\x1b[1m\x1b[31m',
        '*W': '\x1b[1m\x1b[33m',
        '*I': '\x1b[1m\x1b[34m',
        '*V': '',
        '*Vw': '\x1b[33m',
        '*O': '\x1b[1m\x1b[32m',
        '*D': '\x1b[1m\x1b[35m',
        'S': '',
        '': '\x1b[35m',
    }
    LOG_REALLY_EVERYTHING: list[str] = ['']
    LOG_EVERYTHING: list[str] = ['*']
    LOG_NOTHING: list[str] = []
    DEFAULT_TRACEBACK_TAGS: list[str] = ['*E1', '*W', '*Vw']

    log_tags: list[str]
    log_time_tags: list[str]
    log_file_tags: list[str]
    log_stdout_tags: list[str]
    log_stderr_tags: list[str]
    traceback_tags: list[str]
    global_prefixes: list[str]
    use_colors: bool
    init_time: str | None = None

    def __init__(
            self,
            log_tags: list[str] = LOG_EVERYTHING,
            log_time_tags: list[str] = LOG_REALLY_EVERYTHING,
            log_file_tags: list[str] = [*LOG_EVERYTHING, 'f'],
            log_stdout_tags: list[str] = LOG_EVERYTHING,
            log_stderr_tags: list[str] = LOG_NOTHING,
            traceback_tags: list[str] = DEFAULT_TRACEBACK_TAGS,
            global_prefixes: list[str] = [],
            use_colors: bool = True,
    ) -> None:
        self.log_tags = log_tags
        self.log_time_tags = log_time_tags
        self.log_file_tags = log_file_tags
        self.log_stdout_tags = log_stdout_tags
        self.log_stderr_tags = log_stderr_tags
        self.traceback_tags = traceback_tags
        self.global_prefixes = global_prefixes
        self.use_colors = use_colors
        self.init_time = self._current_time()

    @staticmethod
    def _tag_get(tag: str, tag_list: dict[str, str]) -> str:
        for i in reversed(range(len(tag) + 1)):
            if tag[:i] in tag_list:
                return tag_list[tag[:i]]

        return tag_list[''].format(tag)

    @staticmethod
    def _tag_matches(tag: str, tag_list: list[str]) -> bool:
        for i in reversed(range(len(tag) + 1)):
            if tag[:i] in tag_list:
                return True

        return False

    def _colorize(self, tag: str, data: str, force_use_colors: bool | None = None) -> str:
        if not (self.use_colors or force_use_colors):
            return data

        return f'{self._tag_get(tag, self.COLORS)}{data}{self.RESET_COLOR}'

    def _log(
            self,
            tag: str,
            data: str,
            force_log_file: bool | None = None,
            force_log_stdout: bool | None = None,
            force_log_stderr: bool | None = None,
            force_use_colors: bool | None = None,
    ) -> None:
        if self._tag_matches(tag, self.log_file_tags) if force_log_file is None else force_log_file:
            with open(opath.join(opath.dirname(opath.dirname(opath.realpath(__file__))), 'log.txt'), 'a') as file:
                if self.init_time is not None:
                    file.write(f'\n=== Logger initializated at {self.init_time} ===\n')
                    self.init_time = None

                file.write(f'{data}')
                file.flush()

        if self._tag_matches(tag, self.log_stdout_tags) if force_log_stdout is None else force_log_stdout:
            print(self._colorize(tag, data, force_use_colors), end='', flush=True)

        if self._tag_matches(tag, self.log_stderr_tags) if force_log_stderr is None else force_log_stderr:
            print(self._colorize(tag, data, force_use_colors), end='', file=sys.stderr, flush=True)

    @staticmethod
    def _current_time() -> str:
        return str(datetime.now())

    def _global_prefixes(self) -> str:
        if len(self.global_prefixes) == 0:
            return ''

        return f'{' '.join(self.global_prefixes)} '

    def add_global_prefix(self, prefix: str) -> bool:
        if prefix in self.global_prefixes:
            return False

        self.global_prefixes.append(prefix)
        return True

    def remove_global_prefix(self, prefix: str) -> bool:
        if prefix in self.global_prefixes:
            self.global_prefixes.remove(prefix)
            return True

        return False

    def log(
            self,
            tag: str,
            *args,
            sep: str = ' ',
            end: str = '\n',
            force_log_time: bool | None = None,
            **kwargs,
    ) -> None:
        if not self._tag_matches(tag, self.log_tags):
            return

        log_time: bool = self._tag_matches(tag, self.log_time_tags) if force_log_time is None else force_log_time
        text: str = sep.join([str(x) for x in args]) + end
        data: str = f'{f'{self._current_time()} ' if log_time else ''}{self._global_prefixes()}[{self._tag_get(tag, self.TAG_NAMES)}] {text}'

        if self._tag_matches(tag, self.traceback_tags):
            for element in traceback.format_stack()[:-2]:
                for line in element.splitlines(True):
                    data += f'  {line}'

        self._log(tag, data, **kwargs)

    def error3(self, *args, **kwargs) -> None:
        """
        Used to log error from third-party library, hardware or OS itself.
        """
        self.log('*E3', *args, **kwargs)

    def error_pyaudio(self, *args, **kwargs) -> None:
        self.log('*E3p', *args, **kwargs)

    def error_ggwave(self, *args, **kwargs) -> None:
        self.log('*E3g', *args, **kwargs)

    def error(self, *args, **kwargs) -> None:
        self.log('*E1', *args, **kwargs)

    def warning(self, *args, **kwargs) -> None:
        self.log('*W', *args, **kwargs)

    def info(self, *args, **kwargs) -> None:
        self.log('*I', *args, **kwargs)

    def verbose(self, *args, **kwargs) -> None:
        self.log('*V', *args, **kwargs)

    def verbose_batch(self, *args, **kwargs) -> None:
        self.log('*Vb', *args, **kwargs)

    def verbose_coder(self, *args, **kwargs) -> None:
        self.log('*Vc', *args, **kwargs)

    def verbose_frame(self, *args, **kwargs) -> None:
        self.log('*Vf', *args, **kwargs)

    def verbose_stream(self, *args, **kwargs) -> None:
        self.log('*Vs', *args, **kwargs)

    def verbose_ggwave(self, *args, **kwargs) -> None:
        self.log('*Vg', *args, **kwargs)

    def verbose_warning(self, *args, **kwargs) -> None:
        self.log('*Vw', *args, **kwargs)

    def ok(self, *args, **kwargs) -> None:
        self.log('*O', *args, **kwargs)

    def debug(self, *args, **kwargs) -> None:
        self.log('*D', *args, **kwargs)

    def spam(self, *args, **kwargs) -> None:
        self.log('S', *args, **kwargs)

    def file_only(self, *args, **kwargs) -> None:
        self.log('f', *args, **kwargs)

    def is_logging_slow(self) -> bool:
        return self._tag_matches('f', self.log_tags)

    def enable_all(self) -> None:
        pyggwave.GGWave.enable_log()
        self.log_tags = self.LOG_EVERYTHING

    def disable_all(self) -> None:
        pyggwave.GGWave.disable_log()
        self.log_tags = self.LOG_NOTHING


# LOGGER: Logger = Logger(
#     ['I', 'W', 'E', 'Vf', 'Vw', 'O', 'D'],
#     traceback_tags=Logger.DEFAULT_TRACEBACK_TAGS + ['D']
# )
LOGGER: Logger = Logger(
    [*Logger.LOG_EVERYTHING, 'f'],
)

