# micro_spreadsheet

A tiny terminal spreadsheet editor for CSV files.

If you'd like to support me, you can do that here https://github.com/sponsors/wbf22

## Run

```bash
python3 micro_spreadsheet.py [file.csv] [-c]
```

## What it does

- Edit CSV cells in the terminal
- Use formulas like `a1*b1`, `sum()`, `avg()`, trig functions, `log()`, and `ln()`
- Copy, cut, paste, undo, redo
- Wrap cells and assign colors

## Commands

- `d` show the spreadsheet
- `i` inspect a cell
- `c` copy
- `x` cut
- `v` paste
- `z` undo
- `r` redo
- `arrow keys` move around
- `s` save
- `l` load
- `q` quit

## File format

Regular rows are saved as CSV. Extra spreadsheet data is stored at the bottom with `<meta>` lines for formulas, colors, and wrapped cells.
