#!/bin/bash
 
# Description: open several index.html (processed by AFNI) at the same time and do quality control.
# Usage: use the script in the terminal.
# input workdir and IDs and use firefox to open the index.html files
# change the html1 directory
# make sure you load and open the firefox's new window first

# load all modules
ml Flask/3.0.3-GCCcore-13.3.0
ml AFNI/25.1.01-foss-2024a
ml Firefox/141.0

# set up input_dir and input IDs

input_dir="/work/cglab/projects/BRANCH/all_data/for_AFNI/BIDS/branch"

ID=(004 005)

session="01"
prefix="sub-"

# open firefox first then run this script
all_files=()
for id in "${ID[@]}"; do

    subj="${prefix}${id}"
    echo $subj
    
    subj_path="$input_dir/AFNI_derivatives/$subj/ses-${session}"

    if [ -d "$subj_path" ]; then
        html1="$subj_path/kidvid_output/${subj}.results/QC_${subj}/index.html"

        [ -f "$html1" ] && all_files+=("$html1") || echo "Warning: $html1 not found."
    else
        echo "Warning: Directory for subject $subj does not exist."
    fi
done

if [ ${#all_files[@]} -eq 0 ]; then
    echo "No files found to open."
    exit 1
else
    open_apqc.py -infiles "${all_files[@]}"
fi
