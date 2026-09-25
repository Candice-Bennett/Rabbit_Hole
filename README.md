# Rabbit-Hole

Takes a Chinese `.txt` or `.epub`, segments it with HanLP, and tells you how
hard it is against the HSK 2.0, HSK 3.0 and HSK 3.1 word lists. It can also check
AnkiConnect to see how much of the text's vocabulary you already know, and
export the words you're missing to a plain text file that
[Carrot Chunker](https://github.com/Candice-Bennett/Carrot_Chunker) can turn
into Anki cards. The entry point is [main.py](main.py), and the pipeline
steps live under [src](src).

## What it does

- Loads the text (`.txt` or `.epub`) and cleans [Novel-Downloader](https://github.com/404-novel-project/novel-downloader) noise.
- Segments it with HanLP, counting how many times each word appears.
- Compares every word against HSK 2.0, HSK 3.0 and HSK 3.1 and charts the breakdown by
  level.
- Gives you an almost overwhelming amount of data about your text giving an analysis of words
  and hanzi both culumative and unique over the text of the book.
- If `anki_analysis` is on and AnkiConnect is configured, looks up each word against your Anki
  collection and charts the same breakdowns informed by your anki stats
- Offers to export the missing words to a text file, one line per word as
  `word<TAB>count<TAB>example sentence`, where `count` is how many times the
  word occurs in the text and the example is the first sentence the word
  occurs in that's between `example_sentence_min_hanzi` and
  `example_sentence_max_hanzi` hanzi long, falling back to the very first
  sentence the word appears in if none of its sentences fit that range.
  This can then be imported to [Carrot Chunker](https://github.com/Candice-Bennett/Carrot_Chunker) to make anki cards.

This tool does not create Anki cards itself, it only measures difficulty and
tells you what you're missing. Feed the exported word list into
[Carrot Chunker](https://github.com/Candice-Bennett/Carrot_Chunker) to build the cards.

## Example charts

These are just five of the charts Rabbit-Hole makes, A normal run writes many more to `output/`, 
covering new words and hanzi per chapter, cumulative reading, sentence and paragraph length,
HSK lists, and optional Anki and chengyu versions.

![HSK 3.1 breakdown](readme_images/hsk3.1_levels.png)

**Unique new words** - how many new words each chapter throws at you, and the
running total of unique words seen.

![Unique new words](readme_images/unique_new_words.png)

**Occurrences** - every word and hanzi in each chapter, coloured by which time
you're seeing it, so you can see how quickly new vocabulary turns into repeats.

![Occurrences](readme_images/occurrences.png)

**Known coverage (Anki)** - the share of each chapter you'd know, counting a
word or hanzi as known if you know it well in Anki or have already seen it 10
times earlier in the text, against 95% and 98% reading thresholds.

![Known coverage with Anki](readme_images/anki_coverage.png)

**Anki knowledge** - every word split by its status in your Anki collection:
each status's share of every chapter, then cumulative words read and cumulative
unique words seen.

![Anki knowledge](readme_images/anki_knowledge.png)

## Prerequisites

- **Python** - get it from [python.org/downloads](https://www.python.org/downloads/). On Windows,
  tick "Add python.exe to PATH" during install, then confirm it worked with `python --version`
  in a new terminal.
- **AnkiConnect** (only needed for the Anki knowledge check) - in Anki go to Tools > Add-ons > Get Add-ons,
  paste in code `2055492159`, and restart Anki. More info at
  [ankiweb.net/shared/info/2055492159](https://ankiweb.net/shared/info/2055492159).

## Downloading Rabbit-Hole

Click the green "Code" button near the top of this page, then "Download ZIP",
and extract it somewhere.

You'll then need a terminal open *in that folder* to run the commands below. On Windows,
open the extracted folder in File Explorer, click the address bar, type `cmd`, and hit Enter.

## Running Rabbit-Hole

Drop your text (`.txt` or `.epub`) into [data](data), or set `input_path` in
[config.json](config.json).

```
pip install -r requirements.txt
python main.py [name of your file including extension (.txt/.epub)]
```

or, if `input_path` is set in [config.json](config.json):

```
pip install -r requirements.txt
python main.py
```

NOTE: first run downloads the HanLP model (network required, cached after in
`~/.hanlp`).

## Config ([config.json](config.json))

| Flag | What it does |
|---|---|
| `input_path` | `.txt` or `.epub` to read - `""` uses the command-line filename from [data](data) instead |
| `hsk_data_dir` | folder holding the HSK word lists - default [hsk_data](hsk_data) |
| `clean_text` | strip downloader noise (default `true`) |
| `segment_batch_size` | sentences per HanLP call |
| `example_sentence_min_hanzi` | shortest sentence (in hanzi) usable as an example (default `6`) |
| `example_sentence_max_hanzi` | longest sentence (in hanzi) usable as an example (default `20`) |
| `exclude_names` | leave people's names and place names out of every count, chart and export, using HanLP's name tagger (downloads a second model on first run). |
| `seen_times_to_count_as_learned` | for the known coverage charts, once a word or hanzi has been seen this many times in the text, later appearances count as known `0` turns this off |
| `coverage_targets` | dashed reference lines on the known coverage charts, in percent |
| `use_chapters` | uses chapters for charts |
| `chart_bucket_words` | words per bar in the charts when `use_chapters` is `false` |
| `occurrence_bands` | colour bands for the occurrences charts, i.e. `[1, 5, 10, 15, 20]` colours the 1st time a word is seen, the 2nd-5th, 6th-10th, 11th-15th and 16th-20th differently. Occurrences past the last number go in a final band, i.e. 21st+  |
| `occurrence_overflow_band` | show the final band (i.e. 21st+) on the words and hanzi per chapter occurrences charts. |
| `chengyu_analysis` | Makes graphs of all the chengyu (i.e. words with 4+ hanzi) |
| `chart_width_px` / `chart_height_px` | size of every chart image in pixels |
| `chart_x_limits` | `[min, max]` x range for every chart, in chapters (or words read when `use_chapters` is `false`), e.g. `[1, 50]` to show chapters 1-50. `null` shows all  |
| `chart_y_limits` | `[min, max]` y range per chart and panel, keyed by the chart's file name `null` shows all  |
| `ankiconnect_url` | default `http://127.0.0.1:8765` |
| `ankiconnect_timeout` | seconds to wait for AnkiConnect to respond before giving up |
| `mature_interval_days` | interval (in days) a card needs to count as "know well"  |
| `missing_words_output` | where the missing-words export goes - `""` uses `output/missing_words.txt` |
| `anki_analysis` | run the Anki knowledge check, its charts and the missing-words export. |
| `anki_fields` | `{note_type, field_name}` pairs telling it which Anki fields hold the Hanzi word, checked via AnkiConnect. Leave empty (`[]`) to skip the Anki check entirely. |

## Troubleshooting

- **HanLP's model download fails partway through**, with an error along the
  lines of `Chunk 1 downloaded size 197 mismatches with expected size ...`
  HanLP is used to identify the words so is essential. If you run into errors try running it again, if it keeps failing after a
    handful of retries then you can work around it by fetching the file yourself:
    1. Copy the URL from the `Downloading ...` line above the error.
    2. Download it in your browser and unzip it.
    3. Drop the resulting folder into the matching path under `~/.hanlp/` (on Windows this is usually `%APPDATA%\hanlp\`)
       (e.g. `~/.hanlp/tok/coarse_electra_small_20220616_012050/`),
       overwriting anything already there.
    4. Re-run it - it'll see the model's already in place and skip
       downloading it.

## Acknowledgements

The HSK word lists under [hsk_data](hsk_data) are sourced from
[More than enough Hanzi](https://github.com/becky82/mteh) by Rebecca J.
Stones, licensed under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
THANK YOU SO MUCH FOR COLLATING THESE!
