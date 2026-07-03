
# env
conda activate aisr

source ~/anaconda3/bin/activate aisr
cd ~/AISketcher
gnome-terminal --title=AISketcher -- python main.py


# rename image

# run commands
python3 call_AIsketcher.py
python3 sign_aisr.py
python3 draw_trail.py


# Writing:

python3 draw_grid_calibration.py
# check tilt_factor
# change if needed, also in write_words.py

python3 write_words_gui.py 


# Chinese stroke import

# Import real median-path data from hanzi-writer-data into the local font cache
python3 import_hanzi_writer_data.py --text "你好中文一二三人大天小" --skip-missing

# Or import all unique Hanzi found in a UTF-8 text file
python3 import_hanzi_writer_data.py --text-file ./my_dialogue.txt --skip-missing

# Preload a larger everyday seed set from the bundled local corpus
python3 import_hanzi_writer_data.py --text-file ./common_hanzi_seed.txt --skip-missing --max-workers 12

# Dry run a Chinese writing path without moving the robot
python3 write_chinese.py

# Direct Chinese writing with selectable style profiles
# Available styles: regular, kaiti, heiti, songti
python3 -c "from write_chinese import draw_chinese_text_with_robot; draw_chinese_text_with_robot('你好，请问今天有时间吗？', font_name='hanziwriter', style_name='kaiti', x0=290.0, y0=-220.0, dry_run=True, auto_import_missing=True)"
