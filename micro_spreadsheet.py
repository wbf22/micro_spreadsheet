
import argparse
import copy
import os
import re
import signal
import subprocess
import sys
import termios
import tty


'''
Features
- display a csv
- extend, wrap, or truncate overflows
- cell can contain link to image file
- math with references to other cells

'''
ANSII_RESET = "\033[0m"
operators = {'+', '-', '/', '*', '//', '**', '(', ')', ':'}
functions = {'sum', 'avg'}


def convert_cell_name_to_x_y(name: str) -> tuple[int, int]:
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
    x+=1
    
    while x > 0:
        x -= 1  # Decrement x to make the sequence zero-based
        remainder = x % 26
        result.append(chr(ord('a') + remainder))
        x //= 26
    
    return ''.join(reversed(result))


def substitute_if_ref(value: str, equation_targets: {str, float}) -> tuple[bool, str]:

    float_value = 0.0
    try:
        float_value = float(value)
    except ValueError:
        if value in equation_targets:
            if equation_targets[value] != None:
                float_value = equation_targets[value]
            else:
                return True, float_value
        else:
            x, y = convert_cell_name_to_x_y(value)
            if (y < len(cells) and x < len(cells[y])):
                try:
                    float_value = float(cells[y][x])
                except ValueError:
                    return False, cells[y][x]

    return False, float_value


def wrap(width: int, str: str) -> str:
    words = str.split(' ')
    wrapped_str = []
    line_length = 0
    for word in words:
        if line_length + len(word) + 1 > width:
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
            wrapped_str.append(' ')
            wrapped_str.append(word)
            line_length += len(word) + 1
    
    return ''.join(wrapped_str)



def prnt(str: str):
    print(str, end='')

def print_in_color(str: str, rgb_color_code: str) -> str:
    return ''.join([rgb_color_code, str, ANSII_RESET])

def print_red(str: str) -> str:
    return print_in_color(str, '\033[38;2;255;0;0m')

def print_cadet_grey(str: str) -> str:
    # rgb(154, 160, 168)
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

def grey_gradient(i:int, str: str) -> str:
    mod = i % 2
    if mod == 0:
        return print_in_color(str, '\033[38;2;250;250;250m')
    elif mod == 1:
        return print_in_color(str, '\033[38;2;220;220;220m')
def black(str: str) -> str:
    # return print_in_color(str, '\033[38;2;0;0;0m')
    return print_in_color(str, '\033[2m')

def lighter_background(str: str) -> str:
    return print_in_color(str, '\033[48;2;40;40;40m')



def get_float_precision(f):
    s = str(f)
    if '.' in s:
        return len(s.split('.')[1])
    else:
        return 0

def is_cell_name(str: str) -> bool:
    cell_name_regex = r'^[a-zA-Z]+\d+$'  # start, 1 or more alpha, 1 or more digit, finish
    return re.search(cell_name_regex, str)


def tokenize_equation(equation: str) -> list[str]:
    
    equation = " ".join(equation.split(" ")) # remove any double, triple spaces
    
    last = 0
    tokens = []
    for i, c in enumerate(equation):
        if c in operators:
            last_is_op = False if i-1 == 0 else equation[i-1] in operators
            if not last_is_op:
                value = equation[last:i]
                if value != '':
                    tokens.append(value)
            tokens.append(c)
            last = i + 1

    if last != len(equation):
        tokens.append(equation[last:])

    return tokens

def is_equation(str: str) -> bool:
    global operators, functions

    if str == '': return False

    # check for single numbers
    try:
        float(str)
        return False
    except ValueError:

        return str.startswith("=")
        # # split by operators
        # tokens = tokenize_equation(str)
        # number_regex = r'^\d*\.?\d+$'  # start, 0 or more digit, ., 1 or more digit, finish
        # for i, token in enumerate(tokens):
        #     if token not in operators:
        #         if not is_cell_name(token):
        #             is_number = re.search(number_regex, token)
        #             if not is_number:
        #                 next = None if len(tokens) <= i+1 else tokens[i+1]
        #                 is_function = token in functions and next == '('
        #                 if not is_function:
        #                     return False
                

def is_cell_range(str: str) -> bool:
     regex = r'^[a-zA-Z]+\d+:[a-zA-Z]+\d+$'
     return re.search(regex, str)

def convert_cell_range_to_targets(cell_range: str) -> list[tuple[int, int]]:
    cell_names = cell_range.split(':')
    startx, starty = convert_cell_name_to_x_y(cell_names[0])
    endx, endy = convert_cell_name_to_x_y(cell_names[1])

    target_cells = []
    for x in range(startx, endx+1):
        for y in range(starty, endy+1):
            target_cells.append([x, y])
    
    return target_cells


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
        r = g = b = l * 255;
    else:
        c = (1 - abs(2 * l - 1)) * s # Chroma
        x = c * (1 - abs((h / 60) % 2 - 1)); # Secondary component
        m = l - c / 2; # Match lightness

        # Determine RGB values based on hue
        if h >= 0 and h < 60:
            r = c
            g = x
            b = 0
        elif h >= 60 and h < 120:
            r = x
            g = c
            b = 0
        elif h >= 120 and h < 180:
            r = 0
            g = c
            b = x
        elif h >= 180 and h < 240:
            r = 0
            g = x
            b = c
        elif h >= 240 and h < 300:
            r = x
            g = 0
            b = c
        else:
            r = c
            g = 0
            b = x
        

        # Adjust for lightness
        r = round((r + m) * 255)
        g = round((g + m) * 255)
        b = round((b + m) * 255)
    

    return r, g, b


# define arguments
parser = argparse.ArgumentParser(description="A terminal app for editing csv's or making spreadsheets")
parser.add_argument('file', nargs='?', help='path to your csv or spreadsheet file. otherwise a new file is opened')
parser.add_argument('-c', '--commands', required=False, action='store_true', help='whether to show command hints during editing')
args = parser.parse_args()

FILE = args.file
NO_COMMANDS = not args.commands
PRECISION = 4

cells=[['']]
width=1
height=1
equations = {}
colors = {}
wrapped_cell_names = set()
current_cell = 'a0'

actions = []
undone_actions = []

command_stack = []



def set_cell(cells: list[list[str]], x: int, y: int, value: str):
    global width, height, colors

    # add missing cells
    while y >= len(cells):
        cells.append([])
    height = len(cells)
    while x >= len(cells[y]):
        cells[y].append('')
    width = max(width, x+1)

    # set in cells (and format if float)
    if isinstance(value, float):
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
    if cell_name in equations:
        return '=' + equations[cell_name]
    
    return None

def modify_equation(source_cell_name: str, source_x: int, source_y: int, target_x: int, target_y: int) -> str:
    equation = equations[source_cell_name]
    tokens = tokenize_equation(equation)
    for i, token in enumerate(tokens):
        try:
            float(token)
        except ValueError:
            # find equivalent cell
            if token not in operators and token not in functions:
                other_x, other_y = convert_cell_name_to_x_y(token)
                offset_x = other_x - source_x
                offset_y = other_y - source_y
                equivalent_cell_name = convert_x_to_alpha_value(target_x + offset_x) + str(target_y + offset_y)
                tokens[i] = equivalent_cell_name

    return ''.join(tokens)

def set_current_cell(last_x: int, last_y: int):
    global current_cell
    current_cell = convert_x_to_alpha_value(last_x) + str(last_y+1)
    current_value = get_cell(cells, last_x, last_y+1)
    current_value = '' if current_value == None else current_value
    set_cell(cells, last_x, last_y+1, current_value)
    

old_settings = None
fd = None
def handle_exit(signum, frame):
    if old_settings != None and fd != None:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    # Re-enable line wrapping
    print("\033[?7h")


    sys.exit(0)
signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)

def input_f():
    global command_stack, old_settings, fd

    sys.stdout.flush()

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())

        chars = []
        total_in = ''
        ch = ''
        cursor_pos = 0
        command_stack_position = len(command_stack)
        escaped = False
        while ch != '\n' and ch != '\r':
            ch = sys.stdin.read(1)
            if ch == '\n' or ch == '\r':
                break

            if ch == '\t':
                return '\t'

            if not escaped:
                if ch == '\x7f':
                    if len(chars) > 0:
                        if cursor_pos >= len(chars):
                            chars.pop()
                        elif cursor_pos > 0:
                            chars = chars[:cursor_pos-1] + chars[cursor_pos:]

                        if cursor_pos > 0: cursor_pos -= 1
                        
                elif ch == '\x1b':
                    escaped = True
                elif ch == '\x03':
                    os.kill(os.getpid(), signal.SIGINT)
                else:
                    if cursor_pos >= len(chars):
                        chars.append(ch)
                    else:
                        chars = chars[:cursor_pos] + [ch] + chars[cursor_pos:]
                    cursor_pos += 1
            elif escaped:
                ch = sys.stdin.read(1)
                if ch == 'D':
                    if cursor_pos > 0:
                        cursor_pos -= 1
                elif ch == 'C':
                    if cursor_pos < len(total_in):
                        cursor_pos += 1
                elif ch == 'A':
                    if command_stack_position > 0:
                        command_stack_position -= 1
                    if len(command_stack) > command_stack_position:
                        chars = [c for c in command_stack[command_stack_position]]
                        cursor_pos = len(chars)
                elif ch == 'B':
                    if command_stack_position < len(command_stack)-1:
                        command_stack_position += 1
                        chars = [c for c in command_stack[command_stack_position]]
                        cursor_pos = len(chars)
                    else:
                        chars = []
                        cursor_pos = 0

                escaped = False

            total_in = ''.join(chars)
            
            print(f"\033[{4}G", end='') # go to start of line
            print("\033[K", end='') # clear to end of line
            print(total_in, end='') # print chars
            print(f"\r\033[{cursor_pos+3}C", end='')

            
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    print()
    # print('test')
    # print('test')
    # print('test')
    # print('test')

    return ''.join(chars)



def TRIM_CELLS():
    global cells, equations, height, width, current_cell

    current_x, current_y = convert_cell_name_to_x_y(current_cell)
    
    # find last row and column with data
    last_y_with_data = len(cells)
    for y in range(height-1, -1, -1):
        row_has_data = False
        for x in range(0, width):
            value = get_cell(cells, x, y)
            if value != '' and value != None:
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
            value = get_cell(cells, x, y)
            if value != '' and value != None:
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
                if cell_name in equations: del equations[cell_name]

    if last_x_with_data != width:
        for x in range(last_x_with_data, width):
            for y in range(0, height):
                cell_name = convert_x_to_alpha_value(x) + str(y)
                if cell_name in equations: del equations[cell_name]
    
    # set new widths and heights
    width = last_x_with_data
    height = last_y_with_data


    # make default spreadsheet if empty
    if width == height == 0:
        cells = [['']]
        width = 1
        height = 1

def APPLY_EQUATIONS():
    global cells, equations, width, height, operators, functions

    equation_targets = {}
    unresolved_equations = equations.copy()
    last_size = len(unresolved_equations) + 1
    while last_size > len(unresolved_equations):
        last_size = len(unresolved_equations)
        current_unresolved_equations = {}
        for target, equation in unresolved_equations.items():

            failed_to_subsitute = False
            tokens = tokenize_equation(equation)

            substituted_equation = []
            # a3=sum(a1:a2)
            i = 0
            while i < len(tokens):
                token = tokens[i]
                if token not in operators:
                    if token in functions:
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
                        if i+6 < len(tokens): new_tokens.append(token[i+6:])
                        tokens = new_tokens
                        i-=1
                    else:
                        failed_to_subsitute, float_value = substitute_if_ref(token, equation_targets)
                        if failed_to_subsitute: break
                        substituted_equation.append(str(float_value))
                else:
                    substituted_equation.append(token)
                i+=1

            resolution = 0.0
            if not failed_to_subsitute:
                substituted_equation = ''.join(substituted_equation)
                try:
                    resolution = eval(substituted_equation)
                except Exception as e:
                    # nothing
                    resolution = None
                equation_targets[target] = resolution
                x, y = convert_cell_name_to_x_y(target)
                set_cell(cells, x, y, resolution)
            else:
                current_unresolved_equations[target] = equation

        unresolved_equations = current_unresolved_equations

    # add missing cells
    for y in range(len(cells)):
        while len(cells[y]) < width:
            cells[y].append('')

def DISPLAY(show_equations=False):
    global cells, width, height, current_cell, colors

    # clear screen
    print("\033[2J\033[H")

    # determine wrap properties

    column_widths = {i: 4 for i in range(width)}
    row_heights = {i: 1 for i in range(height)}

    for cell_name in wrapped_cell_names:
        x, y = convert_cell_name_to_x_y(cell_name)
        value = get_cell(cells, x, y)
        if show_equations:
            equation = get_equation(x, y)
            if equation != None: value = equation

        column_widths[x] = 10
        val_lines = len(wrap(10, value).split('\n'))
        if val_lines > row_heights[y]:
            row_heights[y] = val_lines

    for y, row in enumerate(cells):
        for x, value in enumerate(row):
            cell_name = convert_x_to_alpha_value(x) + str(y)
            if cell_name not in wrapped_cell_names:
                if show_equations:
                    equation = get_equation(x, y)
                    if equation != None: value = equation
                val_len = len(str(value)) if value != None else len(str('Error'))
                if val_len > column_widths[x]:
                    column_widths[x] = val_len
                

    # column labels
    display = []
    row_label_space = len(str(height))
    display.append(print_cadet_grey(' ' * (row_label_space+2) + '|'))
    for i in range(width):
        alpha_value = convert_x_to_alpha_value(i)
        spaces = column_widths[i] - len(alpha_value)
        first_spaces = spaces // 2 + 1
        second_spaces = spaces - first_spaces + 2
        display.append(" " * first_spaces)
        display.append(light_green(alpha_value[:column_widths[i]]))
        display.append(" " * second_spaces)
        display.append(print_cadet_grey("|"))
    display.append('\n')


    current_x, current_y = convert_cell_name_to_x_y(current_cell)

    # rows
    for y, row in enumerate(cells):

        
        for cell_h in range(row_heights[y]):
            # row label
            display.append(' ')
            row_num_str = str(y)
            if cell_h == 0: display.append(indigo(row_num_str))
            else: display.append(' ' * len(row_num_str))
            display.append(' ' * (row_label_space - len(row_num_str)))
            display.append(print_cadet_grey(' |'))

            # cells
            for x, value in enumerate(row):

                if show_equations:
                    equation = get_equation(x, y)
                    if equation != None: value = equation

                cell_width = column_widths[x]
                cell_name = convert_x_to_alpha_value(x) + str(y)
                cur_line = ''
                if value != None:
                    lines = []
                    if cell_name in wrapped_cell_names:
                        lines = wrap(cell_width, value).split('\n')
                    else:
                        lines = value.split('\n')
                    cur_line = '' if cell_h >= len(lines) else lines[cell_h]
                else: cur_line = 'Error'

                cell_contents = []
                cell_contents.append(' ')
                try:
                    float(cur_line)
                    cell_contents.append(' ' * (cell_width - len(cur_line)))
                    cur_line = str(cur_line)
                    if cell_name in colors: 
                        r, g, b = colors[cell_name]
                        cell_contents.append(print_in_color(cur_line[:cell_width], f'\033[38;2;{r};{g};{b}m')) 
                    else: cell_contents.append(cur_line[:cell_width])
                except ValueError:
                    if cell_name in colors: 
                        r, g, b = colors[cell_name]
                        cell_contents.append(print_in_color(cur_line[:cell_width], f'\033[38;2;{r};{g};{b}m')) 
                    else: cell_contents.append(cur_line[:cell_width])
                    cell_contents.append(' ' * (cell_width - len(cur_line)))
                cell_contents.append(' ')


                if x == current_x and y == current_y:
                    display.append(
                        ''.join([lighter_background(s) for s in cell_contents])
                    )
                else:
                    display.append(
                        ''.join(cell_contents)
                    )

                display.append(print_cadet_grey('|'))

            display.append('\n')


    print(''.join(display))

def get_current_contents(cell_name, x, y):
    global cells, equations
    if cell_name in equations:
        return '=' + equations[cell_name]
    elif y < len(cells) and x < len(cells[y]):
        return tekhelet(cells[y][x])
    else:
        return ''

def LOAD():
    global cells, equations, width, height, FILE, wrapped_cell_names, actions, undone_actions, command_stack, colors

    cells=[['']]
    width=1
    height=1
    equations = {}
    wrapped_cell_names = set()

    actions = []
    undone_actions = []

    command_stack = []


    csv_str = ''
    if (FILE != None and FILE != ''):
        # READ if provided file
        with open(FILE, 'r') as file:
            csv_str = file.read()

        # PARSE CSV
        cells.clear()

        lines = csv_str.split('\n')
        for i, line in enumerate(lines):
            if not line.startswith('<meta>') and line != '':
                line_cells = line.split(',')
                cells.append(line_cells)

        # PARSE META DATA
        for i, line in enumerate(lines):
            if line.startswith('<meta> color '):
                color_set = line.split('<meta> color ')[1]
                target, rgb = color_set.split('=')
                r, g, b = rgb.split(',')
                colors[target] = [int(r), int(g), int(b)]
                recent_colors.append([r,g,b])

            elif line.startswith('<meta>'):
                equation = line.split('<meta>')[1]
                equation = equation.replace(' ', '')
                target, equation = equation.split('=')
                equations[target] = equation


    width = len(cells[0])
    for row in cells:
        if len(row) > width: width = len(row)
    height = len(cells)

def SAVE():
    global cells, FILE, equations

    if FILE == None or FILE == '': 
        print(mint_green('file path: '), end='')
        FILE = input()
    else:
        print(mint_green('saving to ') + FILE)

    with open(FILE, 'w') as file:
        for y, row in enumerate(cells):
            for x, value in enumerate(row):
                file.write(str(value))
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

    
    file.close()

def WRITE_ACTION_FOR_UNDO():
    global cells, width, height, equations, wrapped_cell_names, colors
    actions.append({
        'cells': copy.deepcopy(cells),
        'width': width,
        'height': height,
        'equations': copy.deepcopy(equations),
        'wrapped_cell_names': copy.deepcopy(wrapped_cell_names),
        'colors': copy.deepcopy(colors)
    })

    undone_actions.clear()

def UNDO():
    global cells, width, height, equations, wrapped_cell_names, colors

    if len(actions) == 0: return

    # pop last state
    last_state = actions.pop()

    # add current state to undone actions
    undone_actions.append({
        'cells': copy.deepcopy(cells),
        'width': width,
        'height': height,
        'equations': copy.deepcopy(equations),
        'wrapped_cell_names': copy.deepcopy(wrapped_cell_names),
        'colors': copy.deepcopy(colors)
    })

    # reset to last state
    cells = copy.deepcopy(last_state['cells'])
    width = last_state['width']
    height = last_state['height']
    equations = copy.deepcopy(last_state['equations'])
    wrapped_cell_names = copy.deepcopy(last_state['wrapped_cell_names'])
    colors = copy.deepcopy(last_state['colors'])

def REDO():
    global cells, width, height, equations, wrapped_cell_names, colors
    if len(undone_actions) == 0: return

    # pop undone state
    previous_state = undone_actions.pop()

    # add current state to actions
    actions.append({
        'cells': copy.deepcopy(cells),
        'width': width,
        'height': height,
        'equations': copy.deepcopy(equations),
        'wrapped_cell_names': copy.deepcopy(wrapped_cell_names),
        'colors': copy.deepcopy(colors)
    })

    # reset to undone state
    cells = copy.deepcopy(previous_state['cells'])
    width = previous_state['width']
    height = previous_state['height']
    equations = copy.deepcopy(previous_state['equations'])
    wrapped_cell_names = copy.deepcopy(previous_state['wrapped_cell_names'])
    colors = copy.deepcopy(previous_state['colors'])

def COPY(cell_names: list[str], cut: bool):
    global cells, equations, operators, current_cell,m, colors

    # x a0:b3 a1

    '''
   |       a       |              b              |
 0 | dogs and bats | cats                        |
 1 |            11 |                           3 |
 2 | =a1*b1        | =a1*b1+77                   |
 3 | =avg(a1:a2)   | this is a super long string |
    '''

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
            if source_cell_name not in inserts:
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
    global cells
    COPY(cell_names, True)

def WRAP(command):
    cell_name = command[2:]
    target_cells = []

    WRITE_ACTION_FOR_UNDO()
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

def MOVE():
    global current_cell

    # reprint everything
    TRIM_CELLS()
    APPLY_EQUATIONS()
    DISPLAY()

    sys.stdout.flush()

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    ch = ''
    escaped = False
    while ch != '\n' and ch != '\r':
        
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        if ch == '\n' or ch == '\r':
            break

        x, y = convert_cell_name_to_x_y(current_cell)

        # handle arrow key movement
        if not escaped:
            if ch == '\x1b':
                escaped = True
            elif ch == 'j':
                if x > 0:
                    x -= 1
            elif ch == 'l':
                x += 1
            elif ch == 'i':
                if y > 0:
                    y -= 1
            elif ch == 'k':
                y += 1
        elif escaped:
            ch = sys.stdin.read(1)
            
            if ch == 'D':
                if x > 0:
                    x -= 1
            elif ch == 'C':
                x += 1
            elif ch == 'A':
                if y > 0:
                    y -= 1
            elif ch == 'B':
                y += 1

            escaped = False


        set_current_cell(x, y-1)
        
        print(f"\033[{4}G", end='') # go to start of line
        print("\033[K", end='') # clear to end of line

        # reprint everything
        TRIM_CELLS()
        APPLY_EQUATIONS()
        DISPLAY()
   
def INSERT_ROW():
    global current_cell, width, height
    x, y = convert_cell_name_to_x_y(current_cell)

    last_alpha = convert_x_to_alpha_value(width)

    cut_command = ['a' + str(y) + ':' + last_alpha + str(height), 'a' + str(y+1)]

    CUT(cut_command)

def INSERT_COL():
    global current_cell, width, height
    x, y = convert_cell_name_to_x_y(current_cell)
    curr_alpha = convert_x_to_alpha_value(x)
    next_alpha = convert_x_to_alpha_value(x+1)

    last_alpha = convert_x_to_alpha_value(width)

    cut_command = [curr_alpha + '0' + ':' + last_alpha + str(height), next_alpha + '0']

    CUT(cut_command)

def DELETE_ROW():
    global current_cell, width, height
    x, y = convert_cell_name_to_x_y(current_cell)

    last_alpha = convert_x_to_alpha_value(width)

    cut_command = ['a' + str(y+1) + ':' + last_alpha + str(height), 'a' + str(y)]

    CUT(cut_command)

def DELETE_COL():
    global current_cell, width, height
    x, y = convert_cell_name_to_x_y(current_cell)
    curr_alpha = convert_x_to_alpha_value(x)
    next_alpha = convert_x_to_alpha_value(x+1)

    last_alpha = convert_x_to_alpha_value(width)

    cut_command = [next_alpha + '0' + ':' + last_alpha + str(height), curr_alpha + '0']

    CUT(cut_command)

recent_colors = []
def PICK_COLOR():
    global recent_colors

    WRITE_ACTION_FOR_UNDO()


    h = 130
    s = 80
    l = 25


    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    print("\033[?25l", end='') # hide cursor

    digits=[]
    ch = ''
    escaped = False
    up_down = 0
    while ch != '\n' and ch != '\r':

        print("\033[2J\033[H") # clear screen

        print('RECENTS')
        for i, [rr, rg, rb] in enumerate(recent_colors):
            print(f'\033[48;2;{rr};{rg};{rb}m  ', end='')
            print(ANSII_RESET + ' ' + str(i) + ' ', end='')
            if i % 10 == 9: print()

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
        print(''.join(digits))

        
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        if ch == '\n' or ch == '\r':
            break

        modification = 0

        # handle arrow key movement ( or recent color selction)
        if not escaped:
            if ch == '\x1b':
                escaped = True
            elif ch == 'j':
                modification += 1
            elif ch == 'l':
                modification -= 1
            elif ch == 'i':
                up_down += 1
                up_down = up_down % 3
            elif ch == 'k':
                up_down -= 1
                if up_down < 0: up_down += 3
            elif ch.isdigit():
                digits.append(ch)
                
        elif escaped:
            ch = sys.stdin.read(1)
            
            if ch == 'D':
                modification -= 1
            elif ch == 'C':
                modification += 1
            elif ch == 'A':
                up_down -= 1
                if up_down < 0: up_down += 3
            elif ch == 'B':
                up_down += 1
                up_down = up_down % 3

            escaped = False


        # hue
        if up_down == 0:
            h += modification * 5
            if h < 0: h = 0
            if h > 360: h = 360
        # staturation
        elif up_down == 1:
            s += modification * 5
            if s < 0: s = 0
            if s > 100: s = 100
        # lightness
        elif up_down == 2:
            l += modification
            if l < 0: l = 0
            if l > 100: l = 100

        
    print("\033[?25h", end='') # show cursor
    print(ANSII_RESET, end='') # show cursor
    print("\033[2J\033[H") # clear screen
    
    if len(digits) > 0:
        i = int(''.join(digits))
        r, g, b = recent_colors[i]
    else:
        r, g, b = hsl_to_rgb(h, s, l)
        recent_colors.append([r,g,b])
    
    return r, g, b



# Disable line wrapping
print("\033[?7l")


# do equations and diaply csv
LOAD()
APPLY_EQUATIONS()
DISPLAY()



show_instructions = not NO_COMMANDS

# loop
while True:

    try:

        if show_instructions:
            print(
                ice_blue('d') + tekhelet(' - display the spreadsheet')
            )
            print(
                ice_blue('i <cell>') + tekhelet(' - inspect the equation or value of a cell (or display with equations if no cell is provided)')
            )
            print(
                ice_blue('c <cell or range> <cell> ') + tekhelet(' - copy a cell(s)')
            )
            print(
                ice_blue('x <cell or range> <cell> ') + tekhelet(' - cut a cell(s)')
            )
            print(
                ice_blue('z') + tekhelet(' - undo')
            )
            print(
                ice_blue('r') + tekhelet(' - redo')
            )
            print(
                ice_blue('color') + tekhelet(' - set the color for a cell')
            )
            print(
                ice_blue('w <cell or range>') + tekhelet(' - toogle wrap/extend on a cell')
            )
            print(
                ice_blue('row') + tekhelet(' - insert row above')
            )
            print(
                ice_blue('col') + tekhelet(' - insert col before')
            )
            print(
                ice_blue('drow') + tekhelet(' - delete current row')
            )
            print(
                ice_blue('dcol') + tekhelet(' - delete current col')
            )
            print(
                ice_blue('m') + tekhelet(' - move around with arrow keys or ijkl (hit enter to stop)')
            )
            print(
                ice_blue('m <cell>') + tekhelet(' - to move to a certain cell')
            )
            print(
                ice_blue('h') + tekhelet(' - show commands')
            )
            print(
                ice_blue('l') + tekhelet(' - load file')
            )
            print(
                ice_blue('s') + tekhelet(' - save file')
            )
            print(
                ice_blue('sas') + tekhelet(' - save file as')
            )
            print(
                ice_blue('<tab>') + tekhelet(' - move right')
            )
            print(
                ice_blue('q') + tekhelet(' - quit')
            )
            print(
                mint_green('enter command above or cell(s) to modify')
            )
            show_instructions = False
        print(mint_green('$: '), end='')
        command = input_f()
        command_stack.append(command)
        
        reprint = False
        if command == 'd':
            reprint = True
        elif command == 'i' or command.startswith("i "):
            if len(command) < 2:
                TRIM_CELLS()
                APPLY_EQUATIONS()
                DISPLAY(True)
            else:
                cell_name = command[2:]
                x, y = convert_cell_name_to_x_y(cell_name)
                contents = get_current_contents(cell_name, x, y)
                print()
                print(ice_blue('--- CONTENTS ' + cell_name + ' ---'))
                print(
                    tekhelet(contents)
                )
                print()
        elif command.startswith("c "):
            cell_names = command[2:].split(' ')
            COPY(cell_names, False)
            reprint = True
        elif command.startswith("x "):
            cell_names = command[2:].split(' ')
            CUT(cell_names)
            reprint = True
        elif command == 'z':
            reprint = True
            UNDO()
        elif command == 'r':
            reprint = True
            REDO()
        elif command == 'color':
            reprint = True
            r,g,b = PICK_COLOR()
            colors[current_cell] = [r,g,b]
        elif command.startswith("w "):
            WRAP(command)
            reprint = True
        elif command == 'row':
            reprint = True
            x, y = convert_cell_name_to_x_y(current_cell)
            INSERT_ROW()
            set_current_cell(x, y-1)
        elif command == 'col':
            reprint = True
            x, y = convert_cell_name_to_x_y(current_cell)
            INSERT_COL()
            set_current_cell(x, y-1)
        elif command == 'drow':
            reprint = True
            x, y = convert_cell_name_to_x_y(current_cell)
            DELETE_ROW()
            set_current_cell(x, y-1)
        elif command == 'dcol':
            reprint = True
            x, y = convert_cell_name_to_x_y(current_cell)
            DELETE_COL()
            set_current_cell(x, y-1)
        elif command == 'm':
            MOVE()
        elif command.startswith('m '):
            reprint = True
            cell_name = command[2:]
            x, y = convert_cell_name_to_x_y(cell_name)
            set_current_cell(x, y-1)
        elif command == 'h':
            show_instructions = True
        elif command == 'l':
            print(mint_green('file path: '), end='')
            FILE = input()
            LOAD()
            reprint = True
        elif command == 's':
            SAVE()
        elif command == 'q' or command == 'quit':
            break
        elif command == '\t':
            reprint = True
            x, y = convert_cell_name_to_x_y(current_cell)
            set_current_cell(x+1, y-1)
        elif command == 'sas':
            FILE = None
            SAVE()
        else:
            show_instructions = not NO_COMMANDS
            reprint = True

            # add to stack
            WRITE_ACTION_FOR_UNDO()

            if '=' in command and not command.startswith('='):
                cell_name, value = command.split('=', 1)

                # get input cell(s)
                target_cells = []
                if ':' in cell_name:
                    target_cells = convert_cell_range_to_targets(cell_name)
                else:
                    x, y = convert_cell_name_to_x_y(cell_name)
                    target_cells.append([x, y])

                # set cells
                for x, y in target_cells:
                    target_cell_name = convert_x_to_alpha_value(x) + str(y)
                    if is_equation(value):
                        equations[target_cell_name] = value[1:].replace(" ", "") # remove equals sign and spaces
                    else:
                        if target_cell_name in equations: del equations[target_cell_name]
                        set_cell(cells, x, y, value)
                
                last_x, last_y = target_cells[-1]
                set_current_cell(last_x, last_y)
            
            else:
                value = command
                x, y = convert_cell_name_to_x_y(current_cell)
                if is_equation(value):
                    equations[current_cell] = value[1:].replace(" ", "") # remove equals sign and spaces
                else:
                    if current_cell in equations: del equations[current_cell]
                    set_cell(cells, x, y, value)
                
                set_current_cell(x, y)


        if reprint:
            # display
            TRIM_CELLS()
            APPLY_EQUATIONS()
            DISPLAY()

    except Exception as e:
        print(print_red("\n--- ERROR ---"))
        print(e)
        print()




