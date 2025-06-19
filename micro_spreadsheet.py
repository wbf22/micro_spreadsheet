
import argparse


'''
Features
- display a csv
- extend, wrap, or truncate overflows
- cell can contain link to image file
- math with references to other cells

'''


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
        order = ord(c) - ord('a')
        power = len(col) - 1 - i
        x += 26**power * order


    return x, y


def convert_x_to_alpha_value(x: int):
    power = 1
    while 26**power < x:
        power += 1
    power -= 1

    alpha_value = []
    for i in range(power + 1):
        order = x // (26**(power-i))
        alpha_char = chr(ord('a') + order)
        alpha_value.append(alpha_char)
    
    return ''.join(alpha_value)

def substitute_if_ref(value: str) -> tuple[bool, str]:

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
                    float_value = 0

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
            line_length += len(word)
    
    return wrapped_str




# define arguments
parser = argparse.ArgumentParser(description="A terminal app for editing csv's or making spreadsheets")
parser.add_argument('-f', '--file', required=True, help='path to your csv or spreadsheet file. otherwise a new file is opened')
args = parser.parse_args()

FILE = args.file



# read if provided file
csv_str = ''
if (FILE != None and FILE != ''):
    with open(FILE, 'r') as file:
        csv_str = file.read()



# parse csv
cells=[]
lines = csv_str.split('\n')
for i, line in enumerate(lines):
    if not line.startswith('<meta>'):
        line_cells = line.split(',')
        cells.append(line_cells)

print(cells)


# parse meta data
equation_targets = {}
equations = []
for i, line in enumerate(lines):
    if line.startswith('<meta>'):
        equation = line.split('<meta>')[1]
        equation = equation.replace(' ', '')
        target, equation = equation.split('=')
        equations.append([target, equation])
        equation_targets[target] = None


# apply equations
operators = {'+', '-', '/', '*', '//', '**'}
i = 0
unresolved_equations = equations[:]
last_size = len(unresolved_equations) + 1
while last_size > len(unresolved_equations):
    last_size = len(unresolved_equations)
    current_unresolved_equations = []
    for target, equation in unresolved_equations:


        # expression = "2 + 3 * (4 - 1)"
        # try:
        #     result = eval(expression)
        #     print(result)
        # except SyntaxError as e:
        #     print("SyntaxError:", e)
        # except Exception as e:
        #     print("Error:", e)

        
        failed_to_subsitute = False
        substituted_equation = []
        last = 0
        for i, c in enumerate(equation):
            if c in operators:
                last_is_op = False if i-1 == 0 else equation[i-1] in operators
                if not last_is_op:
                    value = equation[last:i]
                    failed_to_subsitute, float_value = substitute_if_ref(value)
                    if failed_to_subsitute: break
                    substituted_equation.append(str(float_value))
                

                substituted_equation.append(c)
                last = i + 1
        if not failed_to_subsitute:
            value = equation[last:]
            failed_to_subsitute, float_value = substitute_if_ref(value)
            substituted_equation.append(str(float_value))
            

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
            while y >= len(cells):
                cells.append([])
            while x >= len(cells[y]):
                cells[y].append('')
            cells[y][x] = str(resolution)
        else:
            current_unresolved_equations.append(target, equation)

    unresolved_equations = current_unresolved_equations



# DISPLAY 
wrap_mode = 'extend' # extend, wrap, truncate
width = len(cells[0])
for row in cells:
    if len(row) > width: width = len(row)

height = len(cells)


cell_width = 2
cell_height = 1
if wrap_mode == 'extend':
    for row in cells:
        for value in row:
            val_len = len(str(value)) if value != None else len(str('Error'))
            if val_len > cell_width:
                cell_width = val_len
            
elif wrap_mode == 'wrap':
    for row in cells:
        for value in row:
            val_lines = len(wrap(width, value).split('\n'))
            if val_lines > cell_height:
                cell_height = val_lines

elif wrap_mode == 'truncate':
    cell_width = 4


# column labels
row_label_space = len(str(height))
print(' ' * (row_label_space+2), end='|')
for i in range(width):
    alpha_value = convert_x_to_alpha_value(i)
    print(" ", end="")
    print(alpha_value[:cell_width], end="")
    print(" " * (cell_width - len(alpha_value)), end="")
    print(" |", end="")
print()


# rows
for i, row in enumerate(cells):

    
    for cell_h in range(cell_height):
        # row label
        print(' ', end='')
        row_num_str = str(i)
        if cell_h == 0: print(row_num_str, end='')
        else: print(' ' * len(row_num_str), end='')
        print(' ' * (row_label_space - len(row_num_str)), end='')
        print(' |', end='')

        # cells
        for r, value in enumerate(row):
            cur_line = ''
            if value != None:
                lines = value.split('\n')
                cur_line = lines[cell_h]
            else: cur_line = 'Error'

            print(' ', end='')

            try:
                float(cur_line)
                print(' ' * (cell_width - len(cur_line)), end='')
                print(cur_line, end='')
            except ValueError:
                print(cur_line, end='')
                print(' ' * (cell_width - len(cur_line)), end='')

            print(' |', end='')

        print()





