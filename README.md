# Weirdfont: hide a file inside a font

Put **any file** (a photo, a .zip, a song…) inside a **font**, and get the exact same file back out later.

The font still works like a normal font. You can install it and type with it. Nobody can see that a secret is inside.

**Try it now, nothing to install:** https://larsvanranst.github.io/Glyph-Coordinates/

---

## The idea

A letter in a font, like "A", is drawn with dots. Each dot has two numbers: how far it is from the left (x) and how far it is from the bottom (y).

For example, a dot sits at `x = 500, y = 700`.

Now we make a tiny change. If we move a dot by **1** step out of 2000, nobody can see it. It is much smaller than a grain of sand on a football field.

But that tiny change can mean something:

- number is **even** (like 500) = a **0**
- number is **odd** (like 501) = a **1**

So every number is a tiny light switch: off or on. A file is just a long row of 0s and 1s. We set one switch per number, and the file is hidden inside the shape of the letters.

To get the file back, we look at all the numbers in the same order and write down: even, odd, odd, even… and we have the 0s and 1s again.

```
file  ->  0s and 1s  ->  nudge the dots in the font  ->  hidden.ttf
hidden.ttf  ->  look at the dots  ->  0s and 1s  ->  file (same as before!)
```

---

## Use the demo (the easy way)

1. Open https://larsvanranst.github.io/Glyph-Coordinates/ and wait until the top says **Ready.** (the first time takes a few seconds).
2. In box **1. Hide a file**, click and choose a file.
3. Click **Hide it in the font**.
4. Click the download button. The font has your file inside! (A big file does not fit in one font, so you get several fonts in one `.zip`. See "Big files" below.)
5. In box **2. Get it back**, choose the font (or all the fonts, or the `.zip`).
6. Click the download button. You have your file again.

Want to check that it is really the same file? Look at the **SHA-256** line (see "Is it really identical?" below).

---

## Use it yourself on your computer

### 1. Install Python
Download it from https://www.python.org/downloads/ . On Windows, tick **"Add Python to PATH"**.

### 2. Get this project
Click the green **Code** button on GitHub, then **Download ZIP**, and unzip it. Or:
```
git clone https://github.com/LarsVanRanst/Glyph-Coordinates
cd Glyph-Coordinates
```

### 3. Install the one thing it needs
```
pip install fonttools
```
(On Windows you can write `py -m pip install fonttools`.)

### 4. Use it
Windows users write `py` instead of `python` if it doesn't work.

See how much fits in a font:
```
python Weirdfont.py capacity IPAGothic.ttf
```

Hide a file:
```
python Weirdfont.py encode myphoto.jpg IPAGothic.ttf -o hidden.ttf
```

Get it back:
```
python Weirdfont.py decode hidden.ttf -d recovered
```
Your file is now in the folder `recovered`.

If your file was big and you got several fonts (`hidden_001of003.ttf`, …), give `decode` all of them. A pattern or a folder works too:
```
python Weirdfont.py decode "hidden_*.ttf" -d recovered
```

---

## Is it really identical?

"It looks the same" is not good enough. One wrong bit can break a zip. So we compare **fingerprints** (SHA-256). If the fingerprints are the same, every single byte is the same.

Windows:
```
Get-FileHash myphoto.jpg, recovered\myphoto.jpg -Algorithm SHA256
```
Mac / Linux:
```
sha256sum myphoto.jpg recovered/myphoto.jpg
```

Example from my own test (a random 200,000 byte file):

| | SHA-256 |
|---|---|
| before | `4d9828b181b6d5223a97d7fb7718a4cdc829a266ee1430fc165d74267f0cedda` |
| after  | `4d9828b181b6d5223a97d7fb7718a4cdc829a266ee1430fc165d74267f0cedda` |

Same. 🎉

---

## How much fits?

**One bit per number, two numbers per dot.** 8 numbers make 1 byte.

| Font | Space for your file |
|---|---|
| `IPAGothic.ttf` (the default, it has a LOT of letters) | about **229,000 bytes** (~224 KB) |
| DejaVu Sans (a normal font) | about 31,000 bytes (~30 KB) |

More letters and more dots in a font means more room. Files are compressed first (zlib) when that makes them smaller, so text fits better than photos.

**Biggest file I stored:** 600,000 bytes (a random file) spread over 3 copies of `IPAGothic.ttf`, and it came back with the same SHA-256 (`6d873b9d00b4b7629ffc41fa657248c6e8328c9861b882a7307fb8652a4305f1`).

You can also use your own TrueType font in the demo ("Use my own .ttf"), or on the command line, to get more room per font.

## Big files: the pile of fonts

One font is full? No problem. The file is cut into pieces, like a sandwich cut into slices. Each slice goes into its **own copy of the font**. Every font gets a little label saying "I am slice 2 of 3", so you can give them back in **any order**. Missing a slice, or mixing slices from two different files? You get a clear error.

The price: every slice is a whole font. With `IPAGothic.ttf` (6 MB) a 1 MB file needs 5 fonts, so about 30 MB. Big files are slow in the browser, use the command line for those.

---

## What is written inside (the header)

Every font starts with a **chunk label** (44 bytes):

| Part | Size | What it is |
|---|---|---|
| `WFCK` | 4 bytes | "this is a slice of ours" |
| index | 2 bytes | which slice this is (starting at 0) |
| total | 2 bytes | how many slices there are |
| slice length | 4 bytes | how many bytes of data follow |
| group id | 32 bytes | SHA-256 of the whole payload, so slices of different files can't be mixed |

After the slices are put back together, the payload starts with a **file label**, so we know what to read back:

| Part | Size | What it is |
|---|---|---|
| `WFNT` | 4 bytes | "this is one of ours" |
| flags | 1 byte | `1` = the data was compressed |
| name length | 1 byte | how long the file name is |
| data length | 4 bytes | how many bytes of data follow |
| SHA-256 | 32 bytes | the fingerprint of your original file |
| file name | up to 255 bytes | so you get `myphoto.jpg` back |
| data | the rest | your file (maybe compressed) |

All of that is turned into 0s and 1s and hidden in the dots, glyph by glyph, in the order the font lists them. Glyphs that are built from other glyphs (like é = e + ´) or that are empty have no dots of their own, so we skip them.

When decoding, the fingerprint is checked. If it does not match, you get an error and not a broken file.

---

## Good to know

- It needs a **TrueType font** (`.ttf`). Fonts that end in `.otf` (CFF) and "variable" fonts do not work.
- The font must stay **as it is**. If you open it in a font editor and save it again, or convert it, the dots can change and the secret is lost.
- Slices from different files can't be mixed (the group id checks this).
- No error correction yet. The fingerprint tells you if something went wrong, but it can't fix it.
- Everything happens on your own computer. The website runs the same Python file in your browser (with [Pyodide](https://pyodide.org)), and your file is never uploaded.

## How the website works

`index.html` loads Python into your browser, installs `fonttools`, loads `Weirdfont.py`, and calls the same `encode` and `decode` functions you can use on the command line.

## Files in this project

- `Weirdfont.py` is the whole program (about 150 lines).
- `index.html` is the website.
- `IPAGothic.ttf` is the default font. It is licensed by the Information-technology Promotion Agency, Japan under the IPA Font License, see https://ipafont.ipa.go.jp .
