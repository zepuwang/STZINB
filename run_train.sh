#!/bin/bash
commands=(  
  "stdbuf -oL python main_zero_inflated.py --enable-cuda --data-dir ./ny_data_full_60min --save-name pth/STZIMDN_ny_full_60min.pth --log-dir log/stzimdn_60min.txt"    
  "stdbuf -oL python main_zero_inflated.py --enable-cuda --data-dir ./ny_data_full_15min --save-name pth/STZIMDN_ny_full_15min.pth --log-dir log/stzimdn_15min.txt"  
  "stdbuf -oL python main_zero_inflated.py --enable-cuda --data-dir ./ny_data_full_5min --save-name pth/STZIMDN_ny_full_5min.pth --log-dir log/stzimdn_5min.txt"  
)

# Run the first two commands in parallel
for i in {0..1}; do
    current_time=$(date "+%Y.%m.%d-%H.%M.%S")
    echo "Running ${commands[$i]} at $current_time..."
    eval ${commands[$i]} &
done

wait

# Run the last command
current_time=$(date "+%Y.%m.%d-%H.%M.%S")
echo "Running ${commands[4]} at $current_time..."
eval ${commands[2]}

echo "All commands completed."