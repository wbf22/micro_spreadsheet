# micro_spreadsheet

A tiny terminal spreadsheet editor for CSV files.

## Run

```bash
python3 micro_spreadsheet.py [file.csv] [-c]
```

## What it does

- Edit CSV cells in the terminal
- Use formulas like `=a1*b1`, `sum()`, `avg()`, trig functions, `log()`, and `ln()`
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
- `m` move around
- `s` save
- `l` load
- `q` quit

## File format

Regular rows are saved as CSV. Extra spreadsheet data is stored with `<meta>` lines for formulas, colors, and wrapped cells.
