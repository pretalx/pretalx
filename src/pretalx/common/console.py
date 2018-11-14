BOLD = '\033[1m'
RESET = '\033[0m'


def start_box(size):
    try:
        print('┏' + '━' * size + '┓')
    except (UnicodeDecodeError, UnicodeEncodeError):
        print('-' * (size + 2))


def end_box(size):
    try:
        print('┗' + '━' * size + '┛')
    except (UnicodeDecodeError, UnicodeEncodeError):
        print('-' * (size + 2))


def print_line(string, box=False, bold=False, color=None, size=None):
    text_length = len(string)
    alt_string = string
    if bold:
        string = '{}{}{}'.format(BOLD, string, RESET)
    if color:
        string = '{}{}{}'.format(color, string, RESET)
    if box:
        if size:
            if text_length + 2 < size:
                string += ' ' * (size - text_length - 2)
                alt_string += ' ' * (size - text_length - 2)
        string = '┃ {} ┃'.format(string)
        alt_string = '| {} |'.format(string)
    try:
        print(string)
    except (UnicodeDecodeError, UnicodeEncodeError):
        try:
            print(alt_string)
        except (UnicodeDecodeError, UnicodeEncodeError):
            print('unprintable setting')
