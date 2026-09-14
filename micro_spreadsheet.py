import argparse
import copy
import math
import os
import re
import select
import shutil
import signal
import sys
import termios
import tty
'''
Features
- display a csv
- extend, wrap, or truncate overflows
- math with references to other cells
Modes
- NAVIGATE (default): arrows move, shift+arrows select, enter edits, ':' for commands
- EDIT: typing on a cell (arrows commit + move) or enter/F2 (arrows move the text cursor)
- COMMAND: ':' opens a prompt for commands (:c, :x, :v, :z, :r, :row, :color, :s, :q, ...)
'''
ANSII_RESET = "\033[0m"
operators = {'+', '-', '/', '*', '//', '**', '(', ')', ':'}
functions = {'sum', 'avg', 'sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'sinh', 'cosh', 'tanh', 'log', 'ln', 'sqrt'}
constants = {'pi', 'e'}
math_functions = {
    'sin': math.sin,
    'cos': math.cos,
    'tan': math.tan,
    'asin': math.asin,
    'acos': math.acos,
    'atan': math.atan,
    'sinh': math.sinh,
    'cosh': math.cosh,
    'tanh': math.tanh,
    'log': math.log10,
    'ln': math.log,
    'sqrt': math.sqrt,
    'pi': math.pi,
    'e': math.e,
}
# lines printed below the grid (hint/message line + edit prompt)
STATUS_LINES = 2
# ---------------------------------------------------------------------------
# cell name helpers
# ---------------------------------------------------------------------------
def convert_cell_name_to_x_y(name: str) -> tuple[int, int]:
    name = name.lower()
    col = []
    last = 0
    for i, c in enumerate(name):
        last = i
        if c.isdigit():
            break
        col.append(c)
    col = ''.join(col)
    row = []
    for i, c in enumerate(name[last:]):
        if not c.isdigit():
            break
        row.append(c)
    row = ''.join(row)
    y = int(row)
    x = 0
    for i, c in enumerate(col):
        order = ord(c) - ord('a') + 1
        power = len(col) - 1 - i
        x += 26**power * order
    x -= 1
    return x, y
def convert_x_to_alpha_value(x: int):
    result = []
    x += 1
    while x > 0:
        x -= 1  # Decrement x to make the sequence zero-based
        remainder = x % 26
        result.append(chr(ord('a') + remainder))
        x //= 26
    return ''.join(reversed(result))
def is_cell_name(str: str) -> bool:
    cell_name_regex = r'^[a-zA-Z]+\d+$'  # start, 1 or more alpha, 1 or more digit, finish
    return re.search(cell_name_regex, str) is not None
def is_number(str: str) -> bool:
    return re.fullmatch(r'\d*\.?\d+', str) is not None
def is_cell_range(str: str) -> bool:
    regex = r'^[a-zA-Z]+\d+:[a-zA-Z]+\d+$'
    return re.search(regex, str) is not None
def normalize_cell_range(cell_range: str) -> tuple[int, int, int, int]:
    start_cell_name, end_cell_name = cell_range.split(':')
    startx, starty = convert_cell_name_to_x_y(start_cell_name)
    endx, endy = convert_cell_name_to_x_y(end_cell_name)
    if startx > endx:
        startx, endx = endx, startx
    if starty > endy:
        starty, endy = endy, starty
    return startx, starty, endx, endy
def convert_cell_range_to_targets(cell_range: str) -> list[tuple[int, int]]:
    startx, starty, endx, endy = normalize_cell_range(cell_range)
    target_cells = []
    for x in range(startx, endx+1):
        for y in range(starty, endy+1):
            target_cells.append([x, y])
    return target_cells
# ---------------------------------------------------------------------------
# equations
# ---------------------------------------------------------------------------
def substitute_if_ref(value: str, equation_targets: dict) -> tuple[bool, str]:
    float_value = 0.0
    try:
        float_value = float(value)
    except ValueError:
        if value in equation_targets:
            if equation_targets[value] != None:
                float_value = equation_targets[value]
            else:
                return True, float_value
        elif value in equations:
            # an equation that hasn't been evaluated in this pass yet, try again later
            return True, float_value
        else:
            x, y = convert_cell_name_to_x_y(value)
            if y < len(cells) and x < len(cells[y]):
                try:
                    float_value = float(cells[y][x])
                except (ValueError, TypeError):
                    if cells[y][x] == "" or cells[y][x] is None:
                        return False, float_value
                    return False, cells[y][x]
    return False, float_value
def tokenize_equation(equation: str) -> list[str]:
    equation = " ".join(equation.split(" "))  # remove any double, triple spaces
    last = 0
    tokens = []
    for i, c in enumerate(equation):
        if c in operators:
            # capture token before the operator
            last_is_op = False if i-1 == 0 else equation[i-1] in operators
            if not last_is_op:
                value = equation[last:i].replace(" ", "")
                if value != '':
                    tokens.append(value)
            # get the operator as token
            tokens.append(c)
            last = i + 1
        elif c == ' ':
            # ignore space between operators and tokens
            last_is_op = False if i-1 == 0 else equation[i-1] in operators
            next_is_op = False if i+1 >= len(equation) else equation[i+1] in operators
            # otherwise treat as a token
            if not last_is_op and not next_is_op:
                value = equation[last:i].replace(" ", "")
                if value != '':
                    tokens.append(value)
    if last != len(equation):
        tokens.append(equation[last:].replace(" ", ""))
    return tokens
def is_equation(str: str) -> bool:
    global operators, functions
    if str == '': return False
    # check for single numbers
    try:
        float(str)
        return False
    except ValueError:
        # return str.startswith("=")
        # split by operators
        tokens = tokenize_equation(str)
        number_regex = r'^\d*\.?\d+$'  # start, 0 or more digit, ., 1 or more digit, finish
        for i, token in enumerate(tokens):
            if token not in operators:
                if not is_cell_name(token):
                    is_number = re.search(number_regex, token)
                    if not is_number:
                        next = None if len(tokens) <= i+1 else tokens[i+1]
                        is_function = token in functions and next == '('
                        is_constant = token in constants
                        if not is_function and not is_constant:
                            return False           
        return True
# ---------------------------------------------------------------------------
# text helpers and colors
# ---------------------------------------------------------------------------
def wrap(width: int, str: str) -> str:
    words = str.split(' ')
    wrapped_str = []
    line_length = 0
    for word in words:
        needs_space = line_length > 0
        space_needed = 1 if needs_space else 0
        if line_length + len(word) + space_needed > width:
            if len(word) > width:
                remainder = word
                while len(remainder) > width:
                    wrapped_str.append(remainder[:width])
                    wrapped_str.append('\n')
                    remainder = remainder[width:]
                wrapped_str.append(remainder)
                line_length = len(remainder)
            else:
                wrapped_str.append('\n')
                wrapped_str.append(word)
                line_length = len(word)
        else:
            if needs_space:
                wrapped_str.append(' ')
            wrapped_str.append(word)
            line_length += len(word)
            if needs_space:
                line_length += 1
    return ''.join(wrapped_str)
def prnt(str: str):
    print(str, end='')
def print_in_color(str: str, rgb_color_code: str) -> str:
    return ''.join([rgb_color_code, str, ANSII_RESET])
def print_red(str: str) -> str:
    return print_in_color(str, '\033[38;2;255;0;0m')
def print_cadet_grey(str: str) -> str:
    # rgb(35, 36, 38)
    return print_in_color(str, '\033[38;2;35;36;38m')
def print_ash_grey(str: str) -> str:
    # rgb(167, 196, 181)
    return print_in_color(str, '\033[38;2;167;196;181m')
def print_celadon(str: str) -> str:
    # rgb(169, 216, 184)
    return print_in_color(str, '\033[38;2;169;216;184m')
def print_tea_green(str: str) -> str:
    # rgb(190, 255, 199)
    return print_in_color(str, '\033[38;2;190;255;199m')
def print_reseda_green(str: str) -> str:
    # rgb(114, 112, 91)
    return print_in_color(str, '\033[38;2;114;112;91m')
def mint_green(str: str) -> str:
    # 218, 255, 237
    return print_in_color(str, '\033[38;2;218;255;237m')
def ice_blue(str: str) -> str:
    # 155, 243, 240
    return print_in_color(str, '\033[38;2;155;243;240m')
def tekhelet(str: str) -> str:
    # 71, 49, 152
    return print_in_color(str, '\033[38;2;71;49;152m')
def indigo(str: str) -> str:
    # 74, 13, 103
    return print_in_color(str, '\033[38;2;74;13;103m')
def light_green(str: str) -> str:
    # 173, 252, 146
    return print_in_color(str, '\033[38;2;173;252;146m')
def grey_gradient(i: int, str: str) -> str:
    mod = i % 2
    if mod == 0:
        return print_in_color(str, '\033[38;2;250;250;250m')
    return print_in_color(str, '\033[38;2;220;220;220m')
def black(str: str) -> str:
    return print_in_color(str, '\033[2m')
def lighter_background(str: str) -> str:
    return print_in_color(str, '\033[48;2;75;85;110m')
def get_float_precision(f):
    s = str(f)
    if '.' in s:
        return len(s.split('.')[1])
    return 0
def hsl_to_rgb(h, s, l):
    # Normalize hue to [0, 360]
    h = h % 360
    # Normalize saturation and lightness to [0, 1]
    s /= 100
    l /= 100
    r = 0
    g = 0
    b = 0
    if s == 0:
        # Achromatic (gray)
        r = g = b = l
        m = 0
    else:
        c = (1 - abs(2 * l - 1)) * s  # Chroma
        x = c * (1 - abs((h / 60) % 2 - 1))  # Secondary component
        m = l - c / 2  # Match lightness
        # Determine RGB values based on hue
        if 0 <= h < 60:
            r, g, b = c, x, 0
        elif 60 <= h < 120:
            r, g, b = x, c, 0
        elif 120 <= h < 180:
            r, g, b = 0, c, x
        elif 180 <= h < 240:
            r, g, b = 0, x, c
        elif 240 <= h < 300:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x
    # Adjust for lightness
    r = round((r + m) * 255)
    g = round((g + m) * 255)
    b = round((b + m) * 255)
    return r, g, b
# ---------------------------------------------------------------------------
# arguments and state
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(description="A terminal app for editing csv's or making spreadsheets")
parser.add_argument('file', nargs='?', help='path to your csv or spreadsheet file. otherwise a new file is opened')
parser.add_argument('-c', '--commands', required=False, action='store_true', help='whether to show command hints during editing')
args = parser.parse_args()
FILE = args.file
NO_COMMANDS = not args.commands
PRECISION = 4
WRAP_WIDTH = 20
cells = [['']]
width = 1
height = 1
equations = {}
colors = {}
recent_colors = []
wrapped_cell_names = set()
current_cell = 'a0'
selected_cells = []
clip_board = []
clip_board_operation = ""
is_selecting = False
message = ''
actions = []
undone_actions = []
command_stack = []
# ---------------------------------------------------------------------------
# cell access
# ---------------------------------------------------------------------------
def set_cell(cells: list[list[str]], x: int, y: int, value):
    global width, height, colors
    # add missing cells
    while y >= len(cells):
        cells.append([])
        height = len(cells)
    while x >= len(cells[y]):
        cells[y].append('')
        width = max(width, x+1)
    # set in cells (and format if number)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        int_resolution = int(value)
        if int_resolution == value:
            value = int_resolution
        precision = get_float_precision(value)
        precision = min(PRECISION, precision)
        cells[y][x] = f"{value:.{precision}f}"
    else:
        cells[y][x] = value
    # wipe color if blank
    if value == '':
        cell_name = convert_x_to_alpha_value(x) + str(y)
        if cell_name in colors:
            del colors[cell_name]
def get_cell(cells: list[list[str]], x: int, y: int) -> str:
    if y < len(cells):
        if x < len(cells[y]):
            return cells[y][x]
    return None
def get_equation(x: int, y: int) -> str:
    cell_name = convert_x_to_alpha_value(x) + str(y)
    return equations.get(cell_name)
def modify_equation(source_cell_name: str, source_x: int, source_y: int, target_x: int, target_y: int) -> str:
    equation = equations[source_cell_name]
    tokens = tokenize_equation(equation)
    for i, token in enumerate(tokens):
        if is_cell_name(token):
            # find equivalent cell
            other_x, other_y = convert_cell_name_to_x_y(token)
            offset_x = other_x - source_x
            offset_y = other_y - source_y
            equivalent_cell_name = convert_x_to_alpha_value(target_x + offset_x) + str(target_y + offset_y)
            tokens[i] = equivalent_cell_name
    return ''.join(tokens)
def set_current_cell(last_x: int, last_y: int, return_type: str = '\n'):
    global current_cell
    x = last_x
    y = last_y
    if return_type == '\n':
        y += 1
    elif return_type == '\t':
        x += 1
    current_cell = convert_x_to_alpha_value(x) + str(y)
    current_value = get_cell(cells, x, y)
    current_value = '' if current_value == None else current_value
    set_cell(cells, x, y, current_value)
# ---------------------------------------------------------------------------
# terminal input
# ---------------------------------------------------------------------------
def handle_exit(signum=None, frame=None):
    # show cursor, reset colors, re-enable line wrapping
    print(ANSII_RESET + "\033[?25h\033[?7h")
    sys.exit(0)
signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)
KEY_SEQUENCES = {
    '[A': 'UP', '[B': 'DOWN', '[C': 'RIGHT', '[D': 'LEFT',
    'OA': 'UP', 'OB': 'DOWN', 'OC': 'RIGHT', 'OD': 'LEFT',
    '[1;2A': 'SHIFT_UP', '[1;2B': 'SHIFT_DOWN',
    '[1;2C': 'SHIFT_RIGHT', '[1;2D': 'SHIFT_LEFT',
    '[H': 'HOME', '[1~': 'HOME', 'OH': 'HOME',
    '[F': 'END', '[4~': 'END', 'OF': 'END',
    '[3~': 'DELETE',
    'OQ': 'F2', '[12~': 'F2',
}
CONTROL_KEYS = {
    '\r': 'ENTER', '\n': 'ENTER', '\t': 'TAB',
    '\x7f': 'BACKSPACE', '\x08': 'BACKSPACE',
    '\x03': 'CTRL_C',
}
def read_key() -> str:
    """Return a key name ('UP', 'ENTER', 'ESC', ...) or a single printable char."""
    sys.stdout.flush()
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = os.read(fd, 1).decode(errors='ignore')
        if ch == '\x1b':
            # an escape sequence arrives all at once; a lone ESC has nothing after it
            seq = ''
            while select.select([fd], [], [], 0.03)[0]:
                seq += os.read(fd, 1).decode(errors='ignore')
            if seq == '':
                return 'ESC'
            return KEY_SEQUENCES.get(seq, 'UNKNOWN')
        return CONTROL_KEYS.get(ch, ch)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
def edit_line(prompt: str, prompt_len: int, initial: str,
              arrows_commit: bool, history: list[str] | None = None):
    """
    Single line editor.
    prompt_len is the visible length of prompt (without color codes).
    Returns (text or None if cancelled, key that ended editing).
    """
    chars = list(initial)
    pos = len(chars)
    hist_pos = len(history) if history is not None else 0
    while True:
        sys.stdout.write('\r\033[K' + prompt + ''.join(chars))
        sys.stdout.write(f'\033[{prompt_len + pos + 1}G')
        sys.stdout.flush()
        key = read_key()
        if key in ('ENTER', 'TAB'):
            return ''.join(chars), key
        if key in ('ESC', 'CTRL_C'):
            return None, key
        if key in ('LEFT', 'RIGHT', 'UP', 'DOWN') and arrows_commit:
            return ''.join(chars), key
        if key == 'LEFT':
            pos = max(0, pos - 1)
        elif key == 'RIGHT':
            pos = min(len(chars), pos + 1)
        elif key == 'HOME':
            pos = 0
        elif key == 'END':
            pos = len(chars)
        elif key == 'BACKSPACE':
            if pos > 0:
                del chars[pos - 1]
                pos -= 1
        elif key == 'DELETE':
            if pos < len(chars):
                del chars[pos]
        elif key == 'UP' and history:
            hist_pos = max(0, hist_pos - 1)
            chars = list(history[hist_pos])
            pos = len(chars)
        elif key == 'DOWN' and history is not None:
            hist_pos = min(len(history), hist_pos + 1)
            chars = list(history[hist_pos]) if hist_pos < len(history) else []
            pos = len(chars)
        elif len(key) == 1 and key.isprintable():
            chars.insert(pos, key)
            pos += 1
# ---------------------------------------------------------------------------
# sheet processing
# ---------------------------------------------------------------------------
def TRIM_CELLS():
    global cells, equations, height, width, current_cell
    current_x, current_y = convert_cell_name_to_x_y(current_cell)
    # find last row and column with data
    last_y_with_data = len(cells)
    for y in range(height-1, -1, -1):
        row_has_data = False
        for x in range(0, width):
            cell_name = convert_x_to_alpha_value(x) + str(y)
            value = get_cell(cells, x, y)
            if value != '' and value != None:
                row_has_data = True
                break
            elif cell_name in equations:
                row_has_data = True
                break
        if not row_has_data and y < last_y_with_data:
            last_y_with_data = y
        else:
            break
    last_x_with_data = width
    for x in range(width-1, -1, -1):
        column_has_data = False
        for y in range(0, height):
            cell_name = convert_x_to_alpha_value(x) + str(y)
            value = get_cell(cells, x, y)
            if value != '' and value != None:
                column_has_data = True
                break
            elif cell_name in equations:
                column_has_data = True
                break
        if not column_has_data and x < last_x_with_data:
            last_x_with_data = x
        else:
            break
    last_y_with_data = max(last_y_with_data, current_y+1)
    last_x_with_data = max(last_x_with_data, current_x+1)
    # remove empty rows or columns
    cells = cells[:last_y_with_data]
    for y in range(0, len(cells)):
        cells[y] = cells[y][:last_x_with_data]
    # remove equation references
    if last_y_with_data != height:
        for y in range(last_y_with_data, height):
            for x in range(0, width):
                cell_name = convert_x_to_alpha_value(x) + str(y)
                if cell_name in equations:
                    del equations[cell_name]
    if last_x_with_data != width:
        for x in range(last_x_with_data, width):
            for y in range(0, height):
                cell_name = convert_x_to_alpha_value(x) + str(y)
                if cell_name in equations:
                    del equations[cell_name]
    # set new widths and heights
    width = last_x_with_data
    height = last_y_with_data
    # make default spreadsheet if empty
    if width == height == 0:
        cells = [['']]
        width = 1
        height = 1
def APPLY_EQUATIONS():
    global cells, equations, width, height
    equation_targets = {}
    unresolved_equations = equations.copy()
    last_size = len(unresolved_equations) + 1
    while last_size > len(unresolved_equations):
        last_size = len(unresolved_equations)
        current_unresolved_equations = {}
        for target, equation in unresolved_equations.items():
            failed_to_subsitute = False
            invalid = False
            tokens = tokenize_equation(equation.lower())   # evaluate case-insensitively
            substituted_equation = []
            try:
                i = 0
                while i < len(tokens):
                    token = tokens[i]
                    if token in operators:
                        substituted_equation.append(token)
                    elif token in {'sum', 'avg'}:
                        cell_range = tokens[i+2] + tokens[i+3] + tokens[i+4]
                        target_cells = convert_cell_range_to_targets(cell_range)
                        target_cell_names = [convert_x_to_alpha_value(x) + str(y) for x, y in target_cells]
                        new_tokens = tokens[:i]
                        new_tokens.append('(')
                        for target_cell_name in target_cell_names:
                            new_tokens.append(target_cell_name)
                            new_tokens.append("+")
                        new_tokens[-1] = ')'
                        if token == 'avg':
                            new_tokens.append('/')
                            new_tokens.append(str(len(target_cell_names)))
                        new_tokens.extend(tokens[i+6:])
                        tokens = new_tokens
                        i -= 1
                    elif token in math_functions or is_number(token):
                        substituted_equation.append(token)
                    elif is_cell_name(token):
                        failed_to_subsitute, float_value = substitute_if_ref(token, equation_targets)
                        if failed_to_subsitute:
                            break
                        substituted_equation.append(str(float_value))
                    else:
                        # unknown word, only allow known names into eval
                        invalid = True
                        break
                    i += 1
            except Exception:
                invalid = True

            if failed_to_subsitute:
                current_unresolved_equations[target] = equation
                continue

            resolution = None
            if not invalid:
                try:
                    resolution = eval(''.join(substituted_equation), {"__builtins__": {}}, math_functions)
                except Exception:
                    resolution = None
            equation_targets[target] = resolution
            x, y = convert_cell_name_to_x_y(target)
            # show the text the user typed when the equation can't be evaluated
            set_cell(cells, x, y, equation if resolution is None else resolution)
        unresolved_equations = current_unresolved_equations

    # anything still unresolved (circular references, dependencies on broken cells) shows its text too
    for target, equation in unresolved_equations.items():
        x, y = convert_cell_name_to_x_y(target)
        set_cell(cells, x, y, equation)

    # add missing cells
    for y in range(len(cells)):
        while len(cells[y]) < width:
            cells[y].append('')
# ---------------------------------------------------------------------------
# display
# ---------------------------------------------------------------------------
def DISPLAY(show_equations=False):
    global cells, width, height, current_cell, colors
    # clear screen
    print("\033[3J\033[2J\033[H", "")
    sys.stdout.flush()
    # determine wrap properties
    column_widths = {i: 4 for i in range(width)}
    extra_lines = {i: 0 for i in range(height)}
    for cell_name in wrapped_cell_names:
        x, y = convert_cell_name_to_x_y(cell_name)
        value = get_cell(cells, x, y)
        if show_equations:
            equation = get_equation(x, y)
            if equation != None:
                value = equation
        if value != None and x in column_widths and y in extra_lines:
            column_widths[x] = WRAP_WIDTH
            val_lines = len(wrap(WRAP_WIDTH, str(value)).split('\n'))
            if val_lines - 1 > extra_lines[y]:
                extra_lines[y] = val_lines - 1
    for y, row in enumerate(cells):
        for x, value in enumerate(row):
            cell_name = convert_x_to_alpha_value(x) + str(y)
            if cell_name not in wrapped_cell_names:
                if show_equations:
                    equation = get_equation(x, y)
                    if equation != None:
                        value = equation
                val_len = len(str(value)) if value != None else len(str('Error'))
                if val_len > column_widths[x]:
                    column_widths[x] = val_len
    # column labels
    display = []
    row_label_space = len(str(height))
    row_display = []
    row_display.append(print_cadet_grey(' ' * (row_label_space+2) + '|'))
    for i in range(width):
        alpha_value = convert_x_to_alpha_value(i)
        spaces = column_widths[i] - len(alpha_value)
        first_spaces = spaces // 2 + 1
        second_spaces = spaces - first_spaces + 2
        row_display.append(" " * first_spaces)
        row_display.append(light_green(alpha_value[:column_widths[i]]))
        row_display.append(" " * second_spaces)
        row_display.append(print_cadet_grey("|"))
    display.append(''.join(row_display))
    current_x, current_y = convert_cell_name_to_x_y(current_cell)
    selected_start_x, selected_start_y, selected_end_x, selected_end_y = -1, -1, -1, -1
    if len(selected_cells) == 2 and is_selecting:
        selected_start_x, selected_start_y, selected_end_x, selected_end_y = normalize_cell_range(
            selected_cells[0] + ':' + selected_cells[1]
        )
    # rows
    for y, row in enumerate(cells):
        total_lines = 1 + extra_lines[y]
        for cell_h in range(total_lines):
            row_display = []
            if cell_h == 0:
                row_display.append(' ')
                row_num_str = str(y)
                row_display.append(indigo(row_num_str))
                row_display.append(' ' * (row_label_space - len(row_num_str)))
                row_display.append(print_cadet_grey(' |'))
            else:
                row_display.append(' ' * (1 + row_label_space))
                row_display.append(print_cadet_grey(' |'))
            # cells
            for x, value in enumerate(row):
                if show_equations:
                    equation = get_equation(x, y)
                    if equation != None:
                        value = equation
                cell_width = column_widths[x]
                cell_name = convert_x_to_alpha_value(x) + str(y)
                cur_line = ''
                if value != None:
                    if cell_name in wrapped_cell_names:
                        lines = wrap(cell_width, str(value)).split('\n')
                        cur_line = '' if cell_h >= len(lines) else lines[cell_h]
                    elif cell_h == 0:
                        cur_line = str(value)
                else:
                    if cell_h == 0:
                        cur_line = 'Error'
                cell_contents = []
                cell_contents.append(' ')
                try:
                    float(cur_line)
                    # numbers are right aligned
                    cell_contents.append(' ' * (cell_width - len(cur_line)))
                    if cell_name in colors:
                        r, g, b = colors[cell_name]
                        cell_contents.append(print_in_color(cur_line[:cell_width], f'\033[38;2;{r};{g};{b}m'))
                    else:
                        cell_contents.append(cur_line[:cell_width])
                except ValueError:
                    # text is left aligned
                    if cell_name in colors:
                        r, g, b = colors[cell_name]
                        cell_contents.append(print_in_color(cur_line[:cell_width], f'\033[38;2;{r};{g};{b}m'))
                    else:
                        cell_contents.append(cur_line[:cell_width])
                    cell_contents.append(' ' * (cell_width - len(cur_line)))
                cell_contents.append(' ')
                if x == current_x and y == current_y:
                    row_display.append(''.join([lighter_background(s) for s in cell_contents]))
                elif selected_start_x <= x <= selected_end_x and selected_start_y <= y <= selected_end_y:
                    row_display.append(''.join([lighter_background(s) for s in cell_contents]))
                else:
                    row_display.append(''.join(cell_contents))
                row_display.append(print_cadet_grey('|'))
            display.append(''.join(row_display))
    # print display adjusted to fit in view
    size = shutil.get_terminal_size()
    terminal_width = size.columns
    terminal_height = max(4, size.lines - STATUS_LINES)
    current_cell_terminal_x = sum([column_widths[i]+3 for i in range(0, current_x+1)]) + row_label_space+2
    current_cell_terminal_y = sum([1 + extra_lines[i] for i in range(0, current_y+1)]) + 3
    x_adjustment = 0
    cols_skipped = 0
    while current_cell_terminal_x - x_adjustment > terminal_width:
        x_adjustment += column_widths[cols_skipped]+3
        cols_skipped += 1
    y_adjustment = 0
    rows_skipped = 0
    while current_cell_terminal_y - y_adjustment > terminal_height:
        y_adjustment += 1 + extra_lines[rows_skipped]
        rows_skipped += 1
    if cols_skipped > 0:
        cols_skipped += 1
    y_range = min(terminal_height + rows_skipped-1, len(display)+1)
    row_ys = []
    if rows_skipped == 0:
        row_ys = [*range(rows_skipped, y_range)]
    else:
        row_ys = [0, *range(rows_skipped, y_range-1)]
    for y in row_ys:
        if y >= len(display):
            continue
        skipped = 0
        i = 0
        while skipped < cols_skipped and i < len(display[y]):
            if display[y][i] == "|":
                skipped += 1
            i += 1
        x_range = i
        if cols_skipped != 0:
            while skipped < current_x+2 and x_range < len(display[y]):
                if display[y][x_range] == "|":
                    skipped += 1
                x_range += 1
            # row label
            row_label = []
            row_label.append(' ')
            row_num_str = str(y-1) if y > 0 else str(y)
            if y != 0:
                row_label.append(indigo(row_num_str))
            else:
                row_label.append(' ' * (len(row_num_str)))
            row_label.append(' ' * (row_label_space - len(row_num_str)))
            row_label.append(print_cadet_grey(' |'))
            print("".join(row_label), end="")
        else:
            x_range = len(display[y])
        print(display[y][i:i+x_range])
def get_current_contents(cell_name, x, y):
    global cells, equations
    if cell_name in equations:
        return equations[cell_name]
    elif y < len(cells) and x < len(cells[y]):
        return str(cells[y][x])
    else:
        return ''
# ---------------------------------------------------------------------------
# files
# ---------------------------------------------------------------------------
def LOAD():
    global cells, equations, width, height, FILE, wrapped_cell_names, actions, undone_actions, command_stack, colors
    cells = [['']]
    width = 1
    height = 1
    equations = {}
    colors = {}
    wrapped_cell_names = set()
    actions = []
    undone_actions = []
    command_stack = []
    csv_str = ''
    if FILE and os.path.exists(FILE):
        # READ if provided file (a missing file is treated as a new sheet)
        with open(FILE, 'r') as file:
            csv_str = file.read()
    # PARSE CSV
    cells.clear()
    lines = csv_str.split('\n')
    for i, line in enumerate(lines):
        if not line.startswith('<meta>') and line != '':
            line_cells = []
            in_quotes = False
            last = 0
            for c in range(0, len(line)):
                if line[c] == '"' and not in_quotes:
                    in_quotes = True
                elif in_quotes and line[c] == '"' and c+1 < len(line) and line[c+1] != '"' and c-1 > 0 and line[c-1] != '"':
                    in_quotes = False
                elif (line[c] == ',') and not in_quotes:
                    cell = line[last:c]
                    if cell.startswith("\"") and cell.endswith("\""):
                        cell = cell.replace("\"\"", "\"")
                        cell = cell[1:-1]
                    line_cells.append(cell)
                    last = c+1
            cell = line[last:]
            if cell.startswith("\"") and cell.endswith("\""):
                cell = cell.replace("\"\"", "\"")
                cell = cell[1:-1]
            line_cells.append(cell)
            cells.append(line_cells)
    # PARSE META DATA
    for i, line in enumerate(lines):
        if line.startswith('<meta> color '):
            color_set = line.split('<meta> color ')[1]
            target, rgb = color_set.split('=')
            r, g, b = rgb.split(',')
            colors[target] = [int(r), int(g), int(b)]
            if [int(r), int(g), int(b)] not in recent_colors:
                recent_colors.append([int(r), int(g), int(b)])
        elif line.startswith('<meta> wrap '):
            target = line.split('<meta> wrap ')[1]
            wrapped_cell_names.add(target)
        elif line.startswith('<meta>'):
            equation = line.split('<meta>')[1]
            equation = equation.replace(' ', '')
            target, equation = equation.split('=', 1)
            equations[target] = equation
    if len(cells) == 0:
        cells.append([''])
    width = len(cells[0])
    for row in cells:
        if len(row) > width:
            width = len(row)
    height = len(cells)
def SAVE():
    global cells, FILE, equations, wrapped_cell_names
    if FILE == None or FILE == '':
        print(mint_green('file path: '), end='')
        FILE = input()
    with open(FILE, 'w') as file:
        for y, row in enumerate(cells):
            for x, value in enumerate(row):
                formated_val = '' if value is None else str(value)
                if ',' in formated_val:
                    if "\"" in formated_val:
                        formated_val = formated_val.replace("\"", "\"\"")
                    formated_val = f'"{formated_val}"'
                file.write(formated_val)
                if x != len(row)-1:
                    file.write(',')
            file.write('\n')
        for target_cell_name, equation in equations.items():
            file.write('<meta> ')
            file.write(target_cell_name)
            file.write('=')
            file.write(equation)
            file.write('\n')
        for target_cell_name, [r, g, b] in colors.items():
            file.write('<meta> color ')
            file.write(target_cell_name)
            file.write('=')
            file.write(str(r) + ',' + str(g) + ',' + str(b))
            file.write('\n')
        for target_cell_name in wrapped_cell_names:
            file.write('<meta> wrap ')
            file.write(target_cell_name)
            file.write('\n')
# ---------------------------------------------------------------------------
# undo / redo
# ---------------------------------------------------------------------------
def snapshot():
    return {
        'cells': copy.deepcopy(cells),
        'width': width,
        'height': height,
        'equations': copy.deepcopy(equations),
        'wrapped_cell_names': copy.deepcopy(wrapped_cell_names),
        'colors': copy.deepcopy(colors)
    }
def restore(state):
    global cells, width, height, equations, wrapped_cell_names, colors
    cells = copy.deepcopy(state['cells'])
    width = state['width']
    height = state['height']
    equations = copy.deepcopy(state['equations'])
    wrapped_cell_names = copy.deepcopy(state['wrapped_cell_names'])
    colors = copy.deepcopy(state['colors'])
def WRITE_ACTION_FOR_UNDO():
    actions.append(snapshot())
    undone_actions.clear()
def UNDO():
    if len(actions) == 0:
        return
    last_state = actions.pop()
    undone_actions.append(snapshot())
    restore(last_state)
def REDO():
    if len(undone_actions) == 0:
        return
    previous_state = undone_actions.pop()
    actions.append(snapshot())
    restore(previous_state)
# ---------------------------------------------------------------------------
# editing operations
# ---------------------------------------------------------------------------
def COPY(cell_names: list[str], cut: bool):
    global cells, equations, current_cell, colors
    WRITE_ACTION_FOR_UNDO()
    cell_name, target_cell_name = cell_names
    target_start_x, target_start_y = convert_cell_name_to_x_y(target_cell_name)
    source_cells = []
    if ':' in cell_name:
        source_cells = convert_cell_range_to_targets(cell_name)
    else:
        x, y = convert_cell_name_to_x_y(cell_name)
        source_cells.append([x, y])
    startx, starty = source_cells[0]
    # collect current values
    last_x = 0
    last_y = 0
    source_values = []
    for x, y in source_cells:
        # get value
        value = ''
        if y < len(cells) and x < len(cells[y]):
            value = cells[y][x]
        source_cell_name = convert_x_to_alpha_value(x) + str(y)
        r = g = b = None
        if source_cell_name in colors:
            r, g, b = colors[source_cell_name]
        source_values.append([x, y, value, [r, g, b]])
        # wipe cells if cutting
        if cut:
            set_cell(cells, x, y, '')
    # set target values
    new_equations = copy.deepcopy(equations)
    inserts = set()
    for x, y, value, [r, g, b] in source_values:
        offset_from_start_x = x - startx
        offset_from_start_y = y - starty
        target_x = target_start_x + offset_from_start_x
        target_y = target_start_y + offset_from_start_y
        # modify if equation
        source_cell_name = convert_x_to_alpha_value(x) + str(y)
        target_name = convert_x_to_alpha_value(target_x) + str(target_y)
        if source_cell_name in equations:
            value = modify_equation(source_cell_name, x, y, target_x, target_y)
            if source_cell_name not in inserts and cut:
                del new_equations[source_cell_name]
            new_equations[target_name] = value
            inserts.add(target_name)
        else:
            set_cell(cells, target_x, target_y, value)
        # copy colors
        if r != None:
            colors[target_name] = [r, g, b]
        elif target_name in colors:
            del colors[target_name]
        last_x = target_x
        last_y = target_y
    equations = new_equations
    set_current_cell(last_x, last_y)
def CUT(cell_names: list[str]):
    COPY(cell_names, True)
def WRAP(command):
    target_cells = []
    WRITE_ACTION_FOR_UNDO()
    if command == 'w':
        target_cells = convert_cell_range_to_targets(':'.join(selection_range()))
    else:
        cell_name = command[2:].strip().lower()
        if is_cell_range(cell_name):
            target_cells = convert_cell_range_to_targets(cell_name)
        else:
            x, y = convert_cell_name_to_x_y(cell_name)
            target_cells.append([x, y])
    for x, y in target_cells:
        cell_name = convert_x_to_alpha_value(x) + str(y)
        if cell_name in wrapped_cell_names:
            wrapped_cell_names.remove(cell_name)
        else:
            wrapped_cell_names.add(cell_name)
def CLEAR(cell_names: list[str]):
    global cells, equations, wrapped_cell_names, colors
    if len(cell_names) != 2:
        return
    WRITE_ACTION_FOR_UNDO()
    startx, starty, endx, endy = normalize_cell_range(cell_names[0] + ':' + cell_names[1])
    for x in range(startx, endx + 1):
        for y in range(starty, endy + 1):
            cell_name = convert_x_to_alpha_value(x) + str(y)
            set_cell(cells, x, y, '')
            if cell_name in equations:
                del equations[cell_name]
            if cell_name in wrapped_cell_names:
                wrapped_cell_names.remove(cell_name)
            if cell_name in colors:
                del colors[cell_name]
def INSERT_ROW():
    x, y = convert_cell_name_to_x_y(current_cell)
    last_alpha = convert_x_to_alpha_value(width)
    cut_command = ['a' + str(y) + ':' + last_alpha + str(height), 'a' + str(y+1)]
    CUT(cut_command)
def INSERT_COL():
    x, y = convert_cell_name_to_x_y(current_cell)
    curr_alpha = convert_x_to_alpha_value(x)
    next_alpha = convert_x_to_alpha_value(x+1)
    last_alpha = convert_x_to_alpha_value(width)
    cut_command = [curr_alpha + '0' + ':' + last_alpha + str(height), next_alpha + '0']
    CUT(cut_command)
def DELETE_ROW():
    x, y = convert_cell_name_to_x_y(current_cell)
    last_alpha = convert_x_to_alpha_value(width)
    cut_command = ['a' + str(y+1) + ':' + last_alpha + str(height), 'a' + str(y)]
    CUT(cut_command)
def DELETE_COL():
    x, y = convert_cell_name_to_x_y(current_cell)
    curr_alpha = convert_x_to_alpha_value(x)
    next_alpha = convert_x_to_alpha_value(x+1)
    last_alpha = convert_x_to_alpha_value(width)
    cut_command = [next_alpha + '0' + ':' + last_alpha + str(height), curr_alpha + '0']
    CUT(cut_command)
def PICK_COLOR():
    """Returns [r, g, b], or None if cancelled with esc."""
    h = 130
    s = 80
    l = 25
    digits = []
    up_down = 0
    print("\033[?25l", end='')  # hide cursor
    try:
        while True:
            print("\033[2J\033[H")  # clear screen
            print('RECENTS')
            for i, [rr, rg, rb] in enumerate(recent_colors):
                print(f'\033[48;2;{rr};{rg};{rb}m  ', end='')
                print(ANSII_RESET + ' ' + str(i) + ' ', end='')
                if i % 10 == 9:
                    print()
            print()
            print()
            r, g, b = hsl_to_rgb(h, s, l)
            print(f'\033[48;2;{r};{g};{b}m         ')
            print(f'\033[48;2;{r};{g};{b}m         ')
            print(ANSII_RESET, end='')
            if up_down == 0: print('\033[47m\033[30m', end='')
            print('hue' + ANSII_RESET + ' ' + str(h))
            if up_down == 1: print('\033[47m\033[30m', end='')
            print('saturation' + ANSII_RESET + ' ' + str(s))
            if up_down == 2: print('\033[47m\033[30m', end='')
            print('lightness' + ANSII_RESET + ' ' + str(l))
            print()
            print('recent #: ' + ''.join(digits))
            print(tekhelet('up/down pick a value · left/right change it · digits pick a recent · enter accept · esc cancel'))
            key = read_key()
            if key == 'ENTER':
                break
            if key in ('ESC', 'CTRL_C'):
                return None
            modification = 0
            if key in ('RIGHT', 'l'):
                modification = 1
            elif key in ('LEFT', 'j'):
                modification = -1
            elif key in ('UP', 'i'):
                up_down = (up_down - 1) % 3
            elif key in ('DOWN', 'k'):
                up_down = (up_down + 1) % 3
            elif key == 'BACKSPACE' and digits:
                digits.pop()
            elif len(key) == 1 and key.isdigit():
                digits.append(key)
            if up_down == 0:
                h = min(360, max(0, h + modification * 5))
            elif up_down == 1:
                s = min(100, max(0, s + modification * 5))
            elif up_down == 2:
                l = min(100, max(0, l + modification))
    finally:
        print("\033[?25h", end='')  # show cursor
        print(ANSII_RESET, end='')
        print("\033[2J\033[H")  # clear screen
    if len(digits) > 0 and int(''.join(digits)) < len(recent_colors):
        r, g, b = recent_colors[int(''.join(digits))]
    else:
        r, g, b = hsl_to_rgb(h, s, l)
        if [r, g, b] not in recent_colors:
            recent_colors.append([r, g, b])
    return [r, g, b]
# ---------------------------------------------------------------------------
# navigation / modes
# ---------------------------------------------------------------------------
HELP = [
    (':', 'open the command line (up/down for history, esc to cancel)'),
    ('type anything', 'replace the cell (arrows commit and move)'),
    ('enter / F2', 'edit the cell (arrows move the text cursor)'),
    ('arrows', 'move'),
    ('shift+arrows', 'select a range'),
    ('esc', 'clear selection'),
    ('a1*2, sum(a0:a4)', 'equations are detected automatically, bad ones show as text'),
    ('tab', 'commit and move right (while editing) / move right'),
    ('backspace / del', 'clear cell or selection'),
    (':c / :x / :v', 'copy / cut / paste the selection or current cell'),
    (':z / :r', 'undo / redo'),
    (':row / :col', 'insert row above / col before'),
    (':drow / :dcol', 'delete current row / col'),
    (':color', 'set the color of the cell or selection'),
    (':w [cell or range]', 'toggle wrap/extend'),
    (':m <cell>', 'move to a cell'),
    (':c <range> <cell>', 'copy a range to a cell'),
    (':x <range> <cell>', 'cut a range to a cell'),
    (':<range>=<value>', 'set many cells, e.g. :a0:a9=0'),
    (':i [cell]', 'inspect a cell, or show all equations'),
    (':l / :s / :sas', 'load / save / save as'),
    (':q', 'quit'),
    (':h', 'this help'),
]
HINT = ":h help"
MOVES = {'UP': (0, -1), 'DOWN': (0, 1), 'LEFT': (-1, 0), 'RIGHT': (1, 0)}
def redraw():
    global message
    TRIM_CELLS()
    APPLY_EQUATIONS()
    DISPLAY()
    # one line below the grid: a message if there is one, otherwise the hints
    if message:
        print(message)
        message = ''
    elif not NO_COMMANDS:
        # print(tekhelet(HINT))
        pass
def wait_for_key():
    print(tekhelet('press any key to continue'))
    read_key()
def clear_selection():
    global is_selecting
    is_selecting = False
    selected_cells.clear()
def move(dx: int, dy: int, extend: bool):
    global is_selecting
    x, y = convert_cell_name_to_x_y(current_cell)
    if extend and not is_selecting:
        is_selecting = True
        selected_cells[:] = [current_cell, current_cell]
    elif not extend:
        clear_selection()
    set_current_cell(max(0, x + dx), max(0, y + dy), '')
    if extend:
        selected_cells[1] = current_cell
def selection_range() -> tuple[str, str]:
    if is_selecting and len(selected_cells) == 2:
        return selected_cells[0], selected_cells[1]
    return current_cell, current_cell
def commit_cell(x: int, y: int, text: str):
    WRITE_ACTION_FOR_UNDO()
    name = convert_x_to_alpha_value(x) + str(y)
    if is_equation(text.strip()):
        equations[name] = text          # keep exactly what was typed
    else:
        equations.pop(name, None)
    # the cell holds the raw text until APPLY_EQUATIONS replaces it with a result
    set_cell(cells, x, y, text)
def edit_current(initial: str, arrows_commit: bool):
    x, y = convert_cell_name_to_x_y(current_cell)
    text, key = edit_line(mint_green(f"{current_cell}> "), len(current_cell) + 2,
                          initial, arrows_commit)
    if text is None:  # esc: cancel, nothing changes
        return
    # skip the undo entry when the cell was opened and closed unchanged
    if arrows_commit or text != initial:
        commit_cell(x, y, text)
    if key == 'ENTER':
        move(0, 1, False)
    elif key == 'TAB':
        move(1, 0, False)
    elif key in MOVES:
        move(*MOVES[key], False)
def paste():
    global clip_board_operation
    if not clip_board:
        return
    x, y = convert_cell_name_to_x_y(current_cell)
    COPY([f"{clip_board[0]}:{clip_board[1]}", current_cell], clip_board_operation == 'x')
    if clip_board_operation == 'x':
        clip_board_operation = 'c'  # the source is empty now, later pastes copy
    set_current_cell(x, y, '')  # COPY moves the cursor, put it back
def save_with_message():
    global message
    SAVE()
    message = mint_green('saved to ' + str(FILE))
def run_command(command: str):
    """Handles ':' commands. Returns 'quit' to exit."""
    global FILE, message, current_cell, clip_board, clip_board_operation
    command = command.strip()
    x, y = convert_cell_name_to_x_y(current_cell)
    if command in ('q', 'quit'):
        return 'quit'
    elif command == 'h':
        print("\033[2J\033[H")
        for keys, description in HELP:
            print(ice_blue(keys.ljust(26)) + tekhelet(description))
        print()
        wait_for_key()
    # clipboard
    elif command in ('c', 'x'):
        clip_board = list(selection_range())
        clip_board_operation = command
        message = mint_green(('copied ' if command == 'c' else 'cut ') + ':'.join(clip_board))
        clear_selection()
    elif command == 'v':
        if not clip_board:
            message = print_red('nothing to paste, use :c or :x first')
        else:
            paste()
            clear_selection()
    # undo / redo
    elif command in ('z', 'r'):
        if command == 'z':
            UNDO()
        else:
            REDO()
        set_current_cell(x, y, '')  # make sure the cursor cell still exists
    elif command == 'row':
        INSERT_ROW()
        set_current_cell(x, y, '')
    elif command == 'col':
        INSERT_COL()
        set_current_cell(x, y, '')
    elif command == 'drow':
        DELETE_ROW()
        set_current_cell(x, y, '')
    elif command == 'dcol':
        DELETE_COL()
        set_current_cell(x, y, '')
    elif command == 'color':
        rgb = PICK_COLOR()
        if rgb is not None:
            WRITE_ACTION_FOR_UNDO()
            for cx, cy in convert_cell_range_to_targets(':'.join(selection_range())):
                colors[convert_x_to_alpha_value(cx) + str(cy)] = rgb
    elif command == 'w' or command.startswith('w '):
        WRAP(command)
    elif command.startswith('m '):
        cell_name = command[2:].strip().lower()
        if not is_cell_name(cell_name):
            message = print_red(f"not a cell: {cell_name}")
        else:
            clear_selection()
            mx, my = convert_cell_name_to_x_y(cell_name)
            set_current_cell(mx, my, '')
    elif command.startswith('c ') or command.startswith('x '):
        cell_names = command[2:].lower().split()
        if len(cell_names) != 2:
            message = print_red(f"usage: :{command[0]} <cell or range> <cell>")
        else:
            COPY(cell_names, command[0] == 'x')
            set_current_cell(x, y, '')
    elif command == 'i':
        TRIM_CELLS()
        APPLY_EQUATIONS()
        DISPLAY(True)
        wait_for_key()
    elif command.startswith('i '):
        cell_name = command[2:].strip().lower()
        ix, iy = convert_cell_name_to_x_y(cell_name)
        print()
        print(ice_blue('--- CONTENTS ' + cell_name + ' ---'))
        print(tekhelet(get_current_contents(cell_name, ix, iy)))
        print()
        wait_for_key()
    elif command == 'l':
        print()
        print(mint_green('file path: '), end='')
        FILE = input()
        LOAD()
        current_cell = 'a0'
        clear_selection()
    elif command == 's':
        print()
        save_with_message()
    elif command == 'sas':
        print()
        FILE = None
        save_with_message()
    elif '=' in command:
        target, value = command.split('=', 1)
        target = target.strip().lower()
        if is_cell_name(target):
            target = f"{target}:{target}"
        if not is_cell_range(target):
            message = print_red(f"not a cell or range: {target}")
        else:
            for cx, cy in convert_cell_range_to_targets(target):
                commit_cell(cx, cy, value)
    else:
        message = print_red(f"unknown command: {command}  (:h for help)")
# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
# Disable line wrapping
print("\033[?7l", end='')
LOAD()
redraw()
while True:
    try:
        key = read_key()
        # movement and selection
        if key in MOVES:
            move(*MOVES[key], extend=False)
        elif key.startswith('SHIFT_'):
            move(*MOVES[key[6:]], extend=True)
        elif key == 'TAB':
            move(1, 0, extend=False)
        elif key == 'ESC':
            clear_selection()
        # editing
        elif key in ('ENTER', 'F2'):
            x, y = convert_cell_name_to_x_y(current_cell)
            initial = get_equation(x, y)
            if initial is None:
                initial = get_cell(cells, x, y)
            edit_current('' if initial is None else str(initial), arrows_commit=False)
        elif key == ':':
            cmd, _ = edit_line(mint_green('$: '), 3, '', arrows_commit=False, history=command_stack)
            if cmd:
                command_stack.append(cmd)
                if run_command(cmd) == 'quit':
                    break
        elif len(key) == 1 and key.isprintable():
            edit_current(key, arrows_commit=True)
        # clear
        elif key in ('BACKSPACE', 'DELETE'):
            CLEAR(list(selection_range()))
            clear_selection()
            move(0, 1, extend=False)
        redraw()
    except Exception as e:
        print(print_red("\n--- ERROR ---"))
        print(e)
        print()
        wait_for_key()
        try:
            redraw()
        except Exception:
            pass
handle_exit()