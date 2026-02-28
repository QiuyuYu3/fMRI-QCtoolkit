"""
fMRIPrep QC Rating Application
Combines data processing and web interface for rating fMRIPrep quality control reports.

Most people use JSON files instead of CSV for a reason:

- JSON supports nested structures, making it faster to store and process than CSV.
- Parsing CSV to map back to the frontend requires substantial extra code.
- JSON processing is also faster when handling multiple windows (unlikely to open 100 at once?).

Originally, this program outputted CSV, which was suitable for simpler data processing.
Future versions may refactor this script to output JSON if necessary.
"""

import os
import csv
import re
import time
import webbrowser
import threading
import logging
from flask import Flask, render_template, request, jsonify, send_from_directory
from markupsafe import Markup
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from ..utils.port_utils import find_free_port


class FMRIPrepRatingApp:
    """Flask-based rating application for fMRIPrep QC reports."""
    
    # Module name mapping from full names to short identifiers
    MODULE_MAP = {
        "Brain mask and brain tissue segmentation of the T1w": "T1mask",
        "Spatial normalization of the anatomical T1w reference": "Norm",
        "Surface reconstruction": "SurfRecon",
        "Susceptibility distortion correction": "SDC",
        "Alignment of functional and anatomical MRI data (coregistration)": "Align",
        "Brain mask and (anatomical/temporal) CompCor ROIs": "CompCor",
        "Variance explained by t/aCompCor components": "Variance",
        "BOLD Summary": "BOLD",
        "Correlations among nuisance regressors": "Corr",
    }
    
    COMMON_MODULES = ["T1mask", "Norm", "SurfRecon"]
    FUNCTIONAL_MODULES = ["SDC", "Align", "CompCor", "Variance", "BOLD", "Corr"]
    
    def __init__(self, data_dir, output_dir, subjects=None, debug=False):
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.subjects = subjects or []
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG if debug else logging.INFO)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        
        # Setup Flask
        self.app = Flask(__name__)
        self.app.config["DATA_DIR"] = str(self.data_dir)
        self.app.config["OUTPUT_DIR"] = str(self.output_dir)
        self.setup_routes()
    
    def setup_routes(self):
        """Setup Flask routes."""
        
        @self.app.route("/<pid>")
        def participant(pid):
            return self.handle_participant(pid)
        
        @self.app.route("/<pid>/figures/<path:filename>")
        def serve_figures(pid, filename):
            return self.serve_figures(pid, filename)
        
        @self.app.route("/save_ratings", methods=["POST"])
        def save_ratings():
            return self.save_ratings()
    
    def parse_tasks_from_html(self, html_content: str) -> List[Dict[str, any]]:
        """
        By extracting the field beginning with “Reports for:” from the HTML file, locate the session and run numbers. 
        It is possible that both exist, both are missing, or only one is present.
        
        Handles four cases:
        1. "Reports for: session XX, task YY, run Z" (with explicit run)
        2. "Reports for: session XX, task YY" (no run, inferred as 1)
        3. "Reports for: task YY, run Z" (no session)
        4. "Reports for: task YY" (no session, no run)
        
        Returns:
            List of task dictionaries with 'name', 'runs', and 'session' keys
        """
        tasks = []
        seen_tasks = set()
        
        # Case 1: session + task + run (must have ", run" after task)
        pattern1 = r'Reports for:\s*session\s*<span[^>]*>(\d+)</span>[^<]*,\s*task\s*<span[^>]*>(\w+)</span>[^<]*,\s*run\s*<span[^>]*>(\d+)</span>'
        matches1 = re.findall(pattern1, html_content)
        self.logger.debug(f"Case 1 (ses+task+run): {len(matches1)} matches")
        
        if matches1:
            task_runs = {}
            for session, task, run in matches1:
                key = (session, task)
                run_num = int(run)
                task_runs[key] = max(task_runs.get(key, 0), run_num)
            
            for (session, task), max_run in task_runs.items():
                task_key = (session, task, max_run)
                if task_key not in seen_tasks:
                    tasks.append({'name': task, 'runs': max_run, 'session': session})
                    seen_tasks.add(task_key)
        
        # Case 2: session + task (no run - must NOT be followed by ", run")
        pattern2 = r'Reports for:\s*session\s*<span[^>]*>(\d+)</span>[^<]*,\s*task\s*<span[^>]*>(\w+)</span>(?![^<]*,\s*run)'
        matches2 = re.findall(pattern2, html_content)
        self.logger.debug(f"Case 2 (ses+task, no run): {len(matches2)} matches")
        
        for session, task in matches2:
            task_key = (session, task, 1)
            if task_key not in seen_tasks:
                tasks.append({'name': task, 'runs': 1, 'session': session})
                seen_tasks.add(task_key)
        
        # Case 3: task + run (no session - must not have "session" before)
        pattern3 = r'Reports for:\s*(?!.*session)task\s*<span[^>]*>(\w+)</span>[^<]*,\s*run\s*<span[^>]*>(\d+)</span>'
        matches3 = re.findall(pattern3, html_content)
        self.logger.debug(f"Case 3 (task+run, no session): {len(matches3)} matches")
        
        if matches3:
            task_runs_no_session = {}
            for task, run in matches3:
                run_num = int(run)
                task_runs_no_session[task] = max(task_runs_no_session.get(task, 0), run_num)
            
            for task, max_run in task_runs_no_session.items():
                task_key = (None, task, max_run)
                if task_key not in seen_tasks:
                    tasks.append({'name': task, 'runs': max_run, 'session': None})
                    seen_tasks.add(task_key)
        
        # Case 4: task only (no session, no run)
        pattern4 = r'Reports for:\s*(?!.*session)task\s*<span[^>]*>(\w+)</span>(?![^<]*,\s*run)'
        matches4 = re.findall(pattern4, html_content)
        self.logger.debug(f"Case 4 (task only): {len(matches4)} matches")
        
        for task in matches4:
            task_key = (None, task, 1)
            if task_key not in seen_tasks:
                tasks.append({'name': task, 'runs': 1, 'session': None})
                seen_tasks.add(task_key)
        
        # backup format fallback
        if not tasks:
            backup_pattern = r'Task:\s*(\w+)\s*\((\d+)\s*runs?\)'
            backup_matches = re.findall(backup_pattern, html_content)
            for task_name, run_count in backup_matches:
                tasks.append({'name': task_name, 'runs': int(run_count), 'session': None})
        
        # Sort: tasks with session first (by session number), then tasks without session
        tasks.sort(key=lambda x: (x['session'] is None, x['session'] or '', x['name']))
        
        # self.logger.info(f"Parsed {len(tasks)} tasks from HTML")
        return tasks
    
    def process_html_modules(self, html: str) -> Tuple[str, List[List[Dict]]]:
        """
        Process HTML content to insert IDs and track module run count.
        `id` is the navigation name, `name` is the display name.
        Returns:
            Tuple of (processed_html, modules_structure)
        """
        current_session = None
        current_run = None
        session_run_counter = {}
        modules_in_order = []
        seen_task_report = False
        
        combined_pattern = re.compile(r'(<h([23])[^>]*>)(.*?)(</h\2>)', re.DOTALL)
        
        div_run_map = {}  # div_start_pos -> (run, session)
        for m in re.finditer(r'<div\s+id="(datatype-figures[^"]*)"', html):
            div_id = m.group(1)
            run_match = re.search(r'_run-(\d+)', div_id)
            ses_match = re.search(r'_session-(\d+)', div_id)
            if run_match:
                div_run_map[m.start()] = int(run_match.group(1))
        
        def find_enclosing_div_run(pos):
            candidates = [p for p in div_run_map if p < pos]
            if candidates:
                return div_run_map[max(candidates)]
            return None
        
        def replacer(match):
            nonlocal current_session, current_run, seen_task_report
            prefix, tag_level, title, suffix = match.groups()
            
            # Handle h2 tags (session boundaries)
            if tag_level == '2':
                session_match = re.search(r'session\s*<span[^>]*>(\d+)</span>', title)
                if session_match:
                    current_session = session_match.group(1)
                    seen_task_report = True
                    current_run = find_enclosing_div_run(match.start())
                    return match.group(0)
                
                if 'Reports for:' in title and 'task' in title and 'session' not in title:
                    current_session = None
                    current_run = find_enclosing_div_run(match.start())
                    seen_task_report = True
                    return match.group(0)
                
                if not seen_task_report:
                    current_session = None
                
                return match.group(0)
            
            # Handle h3 tags with run-title class
            if tag_level == '3':
                class_match = re.search(r'class=["\']([^"\']*)["\']', prefix)
                if class_match and 'run-title' in class_match.group(1):
                    title_strip = title.strip()
                    if title_strip in self.MODULE_MAP:
                        mod_short = self.MODULE_MAP[title_strip]
                        is_common = mod_short in self.COMMON_MODULES
                        
                        if is_common:
                            id_attr = f'{mod_short}_run-1'
                            display_name = mod_short
                            run_num = 1
                            session_for_storage = None
                        elif current_session is None:
                            key = (title_strip, None)
                            session_run_counter[key] = session_run_counter.get(key, 0) + 1
                            run_num = session_run_counter[key]
                            id_attr = f'{mod_short}_run-{run_num}'
                            display_name = f"{mod_short} r{run_num}"
                            session_for_storage = None
                        else:
                            h3_div_run = find_enclosing_div_run(match.start())
                            if h3_div_run is not None:
                                run_num = h3_div_run
                            else:
                                key = (title_strip, current_session)
                                session_run_counter[key] = session_run_counter.get(key, 0) + 1
                                run_num = session_run_counter[key]
                            
                            id_attr = f'{mod_short}_ses-{current_session}_run-{run_num}'
                            display_name = f"{mod_short} s{current_session} r{run_num}"
                            session_for_storage = current_session
                        
                        modules_in_order.append({
                            "id": id_attr,
                            "name": display_name,
                            "session": session_for_storage,
                            "run": run_num
                        })
                        
                        prefix_no_id = re.sub(r' id=["\'][^"\']*["\']', '', prefix)
                        return f'{prefix_no_id[:-1]} id="{id_attr}">{title_strip}{suffix}'
            
            return match.group(0)
        
        html_processed = combined_pattern.sub(replacer, html)
        
        # Group modules by (session, run)
        run_groups = {}
        anatomical_mods = []
        
        for mod in modules_in_order:
            mod_short_name = mod['id'].split('_')[0]
            
            if mod_short_name in self.COMMON_MODULES:
                anatomical_mods.append(mod)
            else:
                key = (mod['session'], mod['run'])
                if key not in run_groups:
                    run_groups[key] = []
                run_groups[key].append(mod)
        
        # Build final structure
        final_structure = []
        
        if anatomical_mods:
            final_structure.append(anatomical_mods)
        
        # Add functional modules with Final at the end of each group
        for (session, run) in sorted(run_groups.keys(), key=lambda x: (x[0] is None, x[0] or '', x[1])):
            run_modules = run_groups[(session, run)]
            
            if session is None:
                final_id = f"Final_run-{run}"
                final_name = f"Final r{run}"
            else:
                final_id = f"Final_ses-{session}_run-{run}"
                final_name = f"Final s{session} r{run}"
            
            run_modules.append({
                "id": final_id,
                "name": final_name,
                "session": session,
                "run": run
            })
            final_structure.append(run_modules)
        
        # self.logger.info(f"Processed HTML: {len(anatomical_mods)} anatomical modules, {len(run_groups)} run groups")
        return html_processed, final_structure
    
    def load_existing_ratings(self, participant_id: str, html_content: str) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Load previously saved ratings from combined CSV file (subject level)."""
        ratings = {}
        notes = {}
        
        combined_csv = self.output_dir / f"sub-{participant_id}.csv"
        
        if not combined_csv.exists():
            self.logger.debug(f"No combined CSV found for sub-{participant_id}")
            return ratings, notes
        
        tasks = self.parse_tasks_from_html(html_content)
        
        with combined_csv.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                for col, value in row.items():
                    if col == "ID":
                        continue
                    
                    frontend_id = self._map_csv_column_to_frontend_id(col, tasks)
                    
                    if frontend_id:
                        if col.endswith('_r'):
                            ratings[frontend_id] = value or "NA"
                        elif col.endswith('_c'):
                            notes[frontend_id] = value or ""
        
        self.logger.info(f"Loaded {len(ratings)} ratings for sub-{participant_id}")
        return ratings, notes
    
    def _map_csv_column_to_frontend_id(self, col: str, tasks: List[Dict]) -> Optional[str]:
        """Map CSV column name to frontend module ID."""
        col_base = col[:-2] if col.endswith(('_r', '_c')) else col
        
        # Format 1: ses-XX_taskname_ModuleName_localrun
        match1 = re.match(r"^ses-(\d+)_(\w+)_(.+?)_(\d+)$", col_base)
        if match1:
            csv_session, csv_task, mod_name, local_run_str = match1.groups()
            local_run = int(local_run_str)
            
            task_run_start = 1
            for task_info in tasks:
                if task_info['session'] == csv_session and task_info['name'] == csv_task:
                    break
                if task_info['session'] == csv_session:
                    task_run_start += task_info['runs']
            
            global_run = task_run_start + local_run - 1
            
            if mod_name in self.COMMON_MODULES:
                return f"{mod_name}_run-1"
            else:
                return f"{mod_name}_ses-{csv_session}_run-{global_run}"
        
        # Format 2: taskname_ModuleName_localrun (no session)
        no_session_tasks = [t['name'] for t in tasks if t['session'] is None]
        for task_name in no_session_tasks:
            match2 = re.match(f"^{task_name}_([a-zA-Z0-9]+)_(\\d+)$", col_base)
            if match2:
                mod_name, local_run_str = match2.groups()
                local_run = int(local_run_str)
                
                all_module_names = list(self.MODULE_MAP.values()) + ["Final"]
                if mod_name not in all_module_names:
                    continue
                
                task_run_start = 1
                for task_info in tasks:
                    if task_info['name'] == task_name and task_info['session'] is None:
                        break
                    if task_info['session'] is None:
                        task_run_start += task_info['runs']
                
                global_run = task_run_start + local_run - 1
                
                if mod_name in self.COMMON_MODULES:
                    return f"{mod_name}_run-1"
                else:
                    return f"{mod_name}_run-{global_run}"
        
        # Format 3: ModuleName_localrun
        match3 = re.match(r"^([a-zA-Z0-9]+)_(\d+)$", col_base)
        if match3:
            mod_name, local_run_str = match3.groups()
            
            all_module_names = list(self.MODULE_MAP.values()) + ["Final"]
            if mod_name not in all_module_names:
                return None
            
            local_run = int(local_run_str)
            
            if mod_name in self.COMMON_MODULES:
                return f"{mod_name}_run-1"
            else:
                sessions_in_html = [t.get('session') for t in tasks if t.get('session') is not None]
                no_session_tasks = [t for t in tasks if t.get('session') is None]
                
                if sessions_in_html and not no_session_tasks:
                    default_session = min(sessions_in_html)
                    return f"{mod_name}_ses-{default_session}_run-{local_run}"
                else:
                    return f"{mod_name}_run-{local_run}"
        
        return None
    
    def handle_participant(self, pid: str):
        """Handle participant route."""
        pid_clean = pid.strip().lstrip("sub-")
        html_file = self.data_dir / f"sub-{pid_clean}.html"
        
        if not html_file.exists():
            self.logger.error(f"HTML file not found for sub-{pid_clean}")
            return f"<h2>HTML file not found for participant {pid_clean}</h2>", 404
        
        html_content = html_file.read_text(encoding="utf-8")
        
        # Load existing ratings
        all_ratings, all_notes = self.load_existing_ratings(pid_clean, html_content)
        
        # Extract navigation
        nav_matches = re.findall(r'(<nav[\s\S]*?</nav>)', html_content, re.IGNORECASE)
        nav_html = ""
        for nav in nav_matches:
            if "Summary" in nav and "navbar" in nav:
                nav_html = nav
                break
        
        # Process HTML
        processed_html, modules_by_run = self.process_html_modules(html_content)
        
        return render_template(
            "base.html",
            nav_html=nav_html,
            content=Markup(processed_html),
            modules_by_run=modules_by_run,
            ratings_json=all_ratings,
            notes_json=all_notes,
            participant_id=pid_clean
        )
    
    def serve_figures(self, pid: str, filename: str):
        """Serve figure files for a participant."""
        pid_clean = pid.strip().lstrip("sub-")
        base_path = self.data_dir / f"sub-{pid_clean}" / "figures"
        
        if not base_path.exists():
            self.logger.error(f"Figures folder not found for sub-{pid_clean}")
            return "Figures folder not found", 404
        
        return send_from_directory(base_path, filename)
    
    def save_ratings(self):
        """Save user-submitted ratings and comments."""
        data = request.json
        
        if not data or "ratings" not in data or "id" not in data:
            return jsonify({"status": "fail", "message": "Missing ratings or ID"}), 400
        
        participant_id = data["id"].strip().lstrip("sub-")
        ratings = data.get("ratings", {})
        notes = data.get("notes", {})
        
        try:
            html_file = self.data_dir / f"sub-{participant_id}.html"
            html_content = html_file.read_text(encoding="utf-8")
            
            tasks = self.parse_tasks_from_html(html_content)
            
            if not tasks:
                return jsonify({"status": "fail", "message": "No tasks found in HTML"}), 400
            
            # Group tasks by session
            tasks_by_session = {}
            for task_info in tasks:
                session = task_info['session']
                if session not in tasks_by_session:
                    tasks_by_session[session] = []
                tasks_by_session[session].append(task_info)
            
            all_combined_data = {}
            
            # Process each session group
            for session in sorted(tasks_by_session.keys(), key=lambda x: (x is None, x or '')):
                session_tasks = tasks_by_session[session]
                session_run_counter = 1
                
                for task_info in session_tasks:
                    task_name = task_info['name']
                    task_runs = task_info['runs']
                    
                    row_data = {"ID": participant_id}
                    
                    # Common modules
                    for mod in self.COMMON_MODULES:
                        frontend_key = f"{mod}_run-1"
                        row_data[f"{mod}_1_r"] = ratings.get(frontend_key, "NA")
                        row_data[f"{mod}_1_c"] = notes.get(frontend_key, "")
                    
                    # Functional modules + Final
                    for local_run in range(1, task_runs + 1):
                        global_run = session_run_counter + local_run - 1
                        
                        for mod in self.FUNCTIONAL_MODULES:
                            if session is None:
                                frontend_key = f"{mod}_run-{global_run}"
                            else:
                                frontend_key = f"{mod}_ses-{session}_run-{global_run}"
                            
                            row_data[f"{mod}_{local_run}_r"] = ratings.get(frontend_key, "NA")
                            row_data[f"{mod}_{local_run}_c"] = notes.get(frontend_key, "")
                        
                        # Final module
                        if session is None:
                            final_key = f"Final_run-{global_run}"
                        else:
                            final_key = f"Final_ses-{session}_run-{global_run}"
                        
                        row_data[f"Final_{local_run}_r"] = ratings.get(final_key, "NA")
                        row_data[f"Final_{local_run}_c"] = notes.get(final_key, "")
                    
                    # Save per-task CSV
                    if session is None:
                        csv_file = self.output_dir / f"sub-{participant_id}_{task_name}.csv"
                        csv_prefix = task_name
                    else:
                        csv_file = self.output_dir / f"sub-{participant_id}_ses-{session}_{task_name}.csv"
                        csv_prefix = f"ses-{session}_{task_name}"
                    
                    with csv_file.open("w", newline="", encoding="utf-8") as f:
                        writer = csv.DictWriter(f, fieldnames=list(row_data.keys()))
                        writer.writeheader()
                        writer.writerow(row_data)
                    
                    # Collect for combined CSV
                    for key, value in row_data.items():
                        if key != "ID":
                            all_combined_data[f"{csv_prefix}_{key}"] = value
                    
                    session_run_counter += task_runs
            
            # Save combined CSV
            combined_csv = self.output_dir / f"sub-{participant_id}.csv"
            combined_row = {"ID": participant_id, **all_combined_data}
            
            with combined_csv.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(combined_row.keys()))
                writer.writeheader()
                writer.writerow(combined_row)
            
            # self.logger.info(f"Saved ratings for sub-{participant_id}")
            return jsonify({"status": "success"})
            
        except Exception as e:
            self.logger.error(f"Error saving ratings: {e}", exc_info=True)
            return jsonify({"status": "fail", "message": str(e)}), 500
    
    def run_app_and_open_browsers(self, port: int = None):
        """Run the Flask app and open browser tabs for subjects."""
        if port is None:
            port = find_free_port()
        
        self.logger.info(f"Starting server on http://127.0.0.1:{port}")
        
        # If debugging is required, comment this line.
        logging.getLogger('werkzeug').setLevel(logging.ERROR)

        # Start Flask in background thread
        def run_flask():
            self.app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)
        
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        
        # Wait for server to start
        time.sleep(2)
        
        # Open browser tabs
        if self.subjects:
            base_url = f"http://localhost:{port}"
            for subject_id in self.subjects:
                url = f"{base_url}/{subject_id}"
                self.logger.info(f"Opening {url}")
                webbrowser.open(url)
        
        self.logger.info("Server is running. Press Ctrl+C to stop.")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Shutting down server...")