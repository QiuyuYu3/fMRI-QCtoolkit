"""
fMRIPrep QC Rating Application
Combines data processing and web interface for rating fMRIPrep quality control reports.

Reload source vs. export format:
- A JSON sidecar (sub-{ID}.json) stores ratings/notes keyed by frontend module id and
  is the single source of truth when reopening a subject.
- CSV files are still written as an export consumed by the downstream `fmriqc prep` step.

Module ids:
- An id is the short module name plus the entities identifying its report group:
  `_ses-{s}`, `_task-{t}`, `_{acq|ce|rec|dir|echo}-{v}`, `_run-{r}`.
- Only the entities needed to keep ids apart are named. `task` appears when a session
  holds more than one; the others when they vary inside a single (session, task). A
  single-task dataset therefore keeps the short `SDC_ses-01_run-1` form.
- `_run-` carries the BIDS run label, not a position, so the CSV column index matches
  the run numbers in MRIQC's group_bold.tsv. Groups with no run entity count 1..N, skipping labels in use.
"""

import os
import csv
import json
import re
import sys
import time
import webbrowser
import threading
import logging
from flask import Flask, render_template, request, jsonify, send_from_directory
from markupsafe import Markup
from pathlib import Path
from typing import Dict, List, Tuple
from ..utils.access import AccessGate
from ..utils.port_utils import find_free_port
from ..utils.subject_utils import fmriprep_reports


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
    
    # One rating per module; an anatomical <h3> may cover several figures (see README)
    COMMON_MODULES = ["T1mask", "Norm", "SurfRecon"]
    FUNCTIONAL_MODULES = ["SDC", "Align", "CompCor", "Variance", "BOLD", "Corr"]

    # nireports renders group headings as `<h2>Reports for: {entity} <span>{value}</span>, ...</h2>`
    # and repeats them as navbar `<a>` links. Entities vary: session, task, acquisition,
    # ceagent, reconstruction, direction, run, echo -- and fmapid for fieldmap groups.
    GROUP_HEADING_PATTERN = re.compile(r'Reports for:(.*?)</(?:h2|a)>', re.DOTALL)
    GROUP_ENTITY_PATTERN = re.compile(r'([A-Za-z]+)\s*<span[^>]*>([^<]*)</span>')

    # session/task/run shape the module id directly; anything else only earns a place
    # in the id when it takes more than one value inside the same (session, task).
    GROUP_FIXED_ENTITIES = ('session', 'task', 'run')
    ENTITY_ABBREV = {
        'acquisition': 'acq',
        'ceagent': 'ce',
        'reconstruction': 'rec',
        'direction': 'dir',
    }

    # BIDS labels are alphanumeric; anything else could walk out of data_dir/output_dir
    PARTICIPANT_LABEL = re.compile(r'[A-Za-z0-9]+')

    def __init__(self, data_dir, output_dir, subjects=None, debug=False, token=None):
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
        self.gate = AccessGate(self.app, token)
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

    def _participant_label(self, pid):
        """The bare BIDS label, or None when it is not one."""
        if not isinstance(pid, str):
            return None
        label = pid.strip().removeprefix("sub-")
        return label if self.PARTICIPANT_LABEL.fullmatch(label) else None
    
    def _group_entities(self, segment: str) -> Dict[str, str]:
        """BIDS entities of one "Reports for:" heading, keyed by entity name."""
        found = self.GROUP_ENTITY_PATTERN.findall(segment)
        return {k: v.strip() for k, v in found if v.strip() and v.strip() != 'None'}

    def _report_groups(self, html_content: str) -> List[Dict[str, str]]:
        """Functional report groups in document order; fieldmap groups carry no task and are skipped."""
        groups = []
        seen = set()
        for match in self.GROUP_HEADING_PATTERN.finditer(html_content):
            entities = self._group_entities(match.group(1))
            if 'task' not in entities:
                continue
            # The same heading is emitted twice: once in the navbar, once in the body
            identity = tuple(sorted(entities.items()))
            if identity in seen:
                continue
            seen.add(identity)
            groups.append(entities)
        return groups

    def _label_groups(self, groups: List[Dict[str, str]]) -> List[Dict]:
        """Give every group an id suffix, naming only the entities needed to keep it unique."""
        tasks_per_session = {}
        unit_groups = {}
        for entities in groups:
            unit = (entities.get('session'), entities['task'])
            tasks_per_session.setdefault(unit[0], set()).add(unit[1])
            unit_groups.setdefault(unit, []).append(entities)

        # Absence counts as a value, so a group with acq-mb stays apart from one without acq
        def varies(unit, key):
            return len({e.get(key) for e in unit_groups[unit]}) > 1

        staged = []
        explicit_runs = {}
        for entities in groups:
            unit = (entities.get('session'), entities['task'])
            extras = {
                self.ENTITY_ABBREV.get(key, key): value
                for key, value in sorted(entities.items())
                if key not in self.GROUP_FIXED_ENTITIES and varies(unit, key)
            }
            unit_key = unit + (tuple(extras.items()),)
            if 'run' in entities:
                explicit_runs.setdefault(unit_key, set()).add(entities['run'].lstrip('0') or '0')
            staged.append((entities, extras, unit_key))

        labelled = []
        sequence = {}
        for entities, extras, unit_key in staged:
            session, task = unit_key[0], unit_key[1]
            run = entities.get('run')
            if run is None:
                # Skip numbers that another group in the unit carries as its BIDS run label
                n = sequence.get(unit_key, 0) + 1
                while str(n) in explicit_runs.get(unit_key, ()):
                    n += 1
                sequence[unit_key] = n
                run = str(n)

            suffix = f'_ses-{session}' if session is not None else ''
            display = f's{session} ' if session is not None else ''
            if len(tasks_per_session[session]) > 1:
                suffix += f'_task-{task}'
                display += f'{task} '
            for key, value in extras.items():
                suffix += f'_{key}-{value}'
                display += f'{value} '
            suffix += f'_run-{run}'
            display += f'r{run}'

            labelled.append({
                'identity': tuple(sorted(entities.items())),
                'session': session,
                'task': task,
                'extras': extras,
                'run': run,
                'suffix': suffix,
                'display': display,
            })
        return labelled

    def parse_tasks_from_html(self, html_content: str) -> List[Dict[str, any]]:
        """One entry per output CSV: a (session, task) plus any entity that varies inside it."""
        units = {}
        order = []

        for group in self._label_groups(self._report_groups(html_content)):
            key = (group['session'], group['task'], tuple(group['extras'].items()))
            if key not in units:
                units[key] = {
                    'name': group['task'],
                    'session': group['session'],
                    'extras': group['extras'],
                    'runs': [],
                    'suffixes': [],
                }
                order.append(key)
            units[key]['runs'].append(group['run'])
            units[key]['suffixes'].append(group['suffix'])

        tasks = [units[key] for key in order]

        # backup format fallback
        if not tasks:
            backup_pattern = r'Task:\s*(\w+)\s*\((\d+)\s*runs?\)'
            for task_name, run_count in re.findall(backup_pattern, html_content):
                runs = [str(i) for i in range(1, int(run_count) + 1)]
                tasks.append({
                    'name': task_name,
                    'session': None,
                    'extras': {},
                    'runs': runs,
                    'suffixes': [f'_run-{r}' for r in runs],
                })

        # Sessions first (by label), then session-less; document order kept within a session
        tasks.sort(key=lambda x: (x['session'] is None, x['session'] or ''))

        self.logger.debug(f"Parsed {len(tasks)} task units from HTML")
        return tasks

    @staticmethod
    def _anat_id(module: str, session: str = None) -> str:
        return f'{module}_ses-{session}_run-1' if session else f'{module}_run-1'

    def process_html_modules(self, html: str, anat_session: str = None) -> Tuple[str, List[List[Dict]]]:
        """
        Process HTML content to insert IDs and track module run count.
        `id` is the navigation name, `name` is the display name; `anat_session` names a report whose
        anatomy belongs to one session.
        Returns:
            Tuple of (processed_html, modules_structure)
        """
        labelled = self._label_groups(self._report_groups(html))
        group_by_identity = {group['identity']: group for group in labelled}
        group_by_suffix = {group['suffix']: group for group in labelled}

        current_group = None
        modules_in_order = []
        seen_task_report = False

        combined_pattern = re.compile(r'(<h([23])[^>]*>)(.*?)(</h\2>)', re.DOTALL)

        def replacer(match):
            nonlocal current_group, seen_task_report
            prefix, tag_level, title, suffix = match.groups()

            # Handle h2 tags (report group boundaries)
            if tag_level == '2':
                if 'Reports for:' in title:
                    entities = self._group_entities(title.split('Reports for:', 1)[1])
                    label = group_by_identity.get(tuple(sorted(entities.items())))
                    if label is not None:
                        current_group = label
                        seen_task_report = True
                    return match.group(0)

                if not seen_task_report:
                    current_group = None

                return match.group(0)

            # Handle h3 tags with run-title class
            if tag_level == '3':
                class_match = re.search(r'class=["\']([^"\']*)["\']', prefix)
                if class_match and 'run-title' in class_match.group(1):
                    title_strip = title.strip()
                    if title_strip in self.MODULE_MAP:
                        mod_short = self.MODULE_MAP[title_strip]

                        if mod_short in self.COMMON_MODULES:
                            module = {"id": self._anat_id(mod_short, anat_session),
                                      "name": f'{mod_short} s{anat_session}' if anat_session else mod_short,
                                      "session": anat_session, "run": 1, "group": None}
                        elif current_group is None:
                            # A rated module before any group heading: keep the legacy fallback
                            module = {"id": f'{mod_short}_run-1', "name": f'{mod_short} r1',
                                      "session": None, "run": 1, "group": '_run-1'}
                        else:
                            run = current_group['run']
                            module = {
                                "id": f'{mod_short}{current_group["suffix"]}',
                                "name": f'{mod_short} {current_group["display"]}',
                                "session": current_group['session'],
                                "run": int(run) if run.isdigit() else run,
                                "group": current_group['suffix'],
                            }

                        modules_in_order.append(module)

                        prefix_no_id = re.sub(r' id=["\'][^"\']*["\']', '', prefix)
                        return f'{prefix_no_id[:-1]} id="{module["id"]}">{title_strip}{suffix}'

            return match.group(0)

        html_processed = combined_pattern.sub(replacer, html)

        # Group modules by report group, in document order
        run_groups = {}
        group_order = []
        anatomical_mods = []

        for mod in modules_in_order:
            if mod['group'] is None:
                anatomical_mods.append(mod)
            else:
                if mod['group'] not in run_groups:
                    run_groups[mod['group']] = []
                    group_order.append(mod['group'])
                run_groups[mod['group']].append(mod)

        # Build final structure
        final_structure = []

        if anatomical_mods:
            final_structure.append(anatomical_mods)

        # Add functional modules with Final at the end of each group
        for group_suffix in group_order:
            run_modules = run_groups[group_suffix]
            label = group_by_suffix.get(group_suffix)

            run_modules.append({
                "id": f"Final{group_suffix}",
                "name": f"Final {label['display']}" if label else "Final r1",
                "session": run_modules[0]['session'],
                "run": run_modules[0]['run'],
                "group": group_suffix,
            })
            final_structure.append(run_modules)

        # `group` is internal bookkeeping and never reaches the frontend
        for module in modules_in_order + [m for g in final_structure for m in g]:
            module.pop("group", None)

        return html_processed, final_structure
    
    def load_existing_ratings(self, participant_id: str) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Load previously saved ratings from the JSON sidecar (subject level)."""
        json_file = self.output_dir / f"sub-{participant_id}.json"

        if not json_file.exists():
            self.logger.debug(f"No JSON ratings found for sub-{participant_id}")
            return {}, {}

        with json_file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        ratings = data.get("ratings", {})
        notes = data.get("notes", {})

        self.logger.info(f"Loaded {len(ratings)} ratings for sub-{participant_id}")
        return ratings, notes

    def _report_pages(self, participant_id: str) -> List[Tuple[str, str]]:
        """The participant's report files, read in page order, each with its anatomy's session (None: shared)."""
        reports, _ = fmriprep_reports(self.data_dir, participant_id)
        return [(path.read_text(encoding="utf-8"), session) for path, session in reports]

    @staticmethod
    def _body_without_nav(html: str) -> str:
        """A later report's body, without the fixed navbar that would cover the first report's."""
        body = re.search(r'<body[^>]*>(.*)</body>', html, re.DOTALL | re.IGNORECASE)
        return re.sub(r'<nav[\s\S]*?</nav>', '', body.group(1) if body else html, flags=re.IGNORECASE)

    def _warn_unsupported_entities(self, participant_id: str, tasks: List[Dict]):
        """Say up front that acquisition/direction variants get rated but not plotted."""
        split_units = [t for t in tasks if t['extras']]
        if not split_units:
            return

        entities = sorted({f"{k}-{v}" for unit in split_units for k, v in unit['extras'].items()})
        self.logger.warning(
            f"sub-{participant_id}: task(s) split by {', '.join(entities)}. "
            "Ratings are saved, but `fmriqc prep` cannot feed them to the dashboard yet."
        )

    def handle_participant(self, pid: str):
        """Handle participant route."""
        pid_clean = self._participant_label(pid)
        if pid_clean is None:
            return "<h2>Invalid participant label</h2>", 404
        pages = self._report_pages(pid_clean)

        if not pages:
            self.logger.error(f"HTML file not found for sub-{pid_clean}")
            return f"<h2>HTML file not found for participant {pid_clean}</h2>", 404

        # Load existing ratings
        all_ratings, all_notes = self.load_existing_ratings(pid_clean)

        # Extract navigation
        nav_matches = re.findall(r'(<nav[\s\S]*?</nav>)', pages[0][0], re.IGNORECASE)
        nav_html = ""
        for nav in nav_matches:
            if "Summary" in nav and "navbar" in nav:
                nav_html = nav
                break

        # One page for all of the participant's reports, in order
        contents, modules_by_run, tasks = [], [], []
        for i, (html_content, anat_session) in enumerate(pages):
            processed_html, groups = self.process_html_modules(html_content, anat_session)
            contents.append(processed_html if i == 0 else self._body_without_nav(processed_html))
            modules_by_run += groups
            tasks += self.parse_tasks_from_html(html_content)

        self._warn_unsupported_entities(pid_clean, tasks)

        return render_template(
            "base.html",
            nav_html=nav_html,
            content=Markup("".join(contents)),
            modules_by_run=modules_by_run,
            ratings_json=all_ratings,
            notes_json=all_notes,
            participant_id=pid_clean
        )
    
    def serve_figures(self, pid: str, filename: str):
        """Serve figure files for a participant."""
        pid_clean = self._participant_label(pid)
        if pid_clean is None:
            return "Invalid participant label", 404
        base_path = self.data_dir / f"sub-{pid_clean}" / "figures"
        
        if not base_path.exists():
            self.logger.error(f"Figures folder not found for sub-{pid_clean}")
            return "Figures folder not found", 404
        
        return send_from_directory(base_path, filename)
    
    def save_ratings(self):
        """Save user-submitted ratings and comments."""
        data = request.get_json(silent=True)

        if not isinstance(data, dict) or "ratings" not in data or "id" not in data:
            return jsonify({"status": "fail", "message": "Missing ratings or ID"}), 400

        participant_id = self._participant_label(data["id"])
        if participant_id is None:
            return jsonify({"status": "fail", "message": "Invalid participant label"}), 400
        ratings = data.get("ratings", {})
        notes = data.get("notes", {})
        if not isinstance(ratings, dict) or not isinstance(notes, dict):
            return jsonify({"status": "fail", "message": "Ratings and notes must be objects"}), 400
        
        try:
            pages = self._report_pages(participant_id)
            if not pages:
                raise FileNotFoundError(f"HTML file not found for participant {participant_id}")

            # The sidecar is what a reopened page reads, so it must not depend on the CSV export succeeding
            json_file = self.output_dir / f"sub-{participant_id}.json"
            with json_file.open("w", encoding="utf-8") as f:
                json.dump({"ratings": ratings, "notes": notes}, f, ensure_ascii=False, indent=2)

            def common_data(anat_session):
                data = {}
                for mod in self.COMMON_MODULES:
                    frontend_key = self._anat_id(mod, anat_session)
                    data[f"{mod}_1_r"] = ratings.get(frontend_key, "NA")
                    data[f"{mod}_1_c"] = notes.get(frontend_key, "")
                return data

            tasks = [(task, anat_session) for html_content, anat_session in pages
                     for task in self.parse_tasks_from_html(html_content)]

            # An anatomical-only report still gets a subject-level export
            all_combined_data = {}
            if not tasks:
                for _, anat_session in pages:
                    prefix = f"ses-{anat_session}_" if anat_session else ""
                    all_combined_data.update({prefix + k: v for k, v in common_data(anat_session).items()})

            for task_info, anat_session in tasks:
                session = task_info['session']
                task_name = task_info['name']

                row_data = {"ID": participant_id, **common_data(anat_session)}

                # Functional modules + Final, one column set per report group.
                # The column index is the BIDS run label, so it lines up with group_bold.tsv.
                for run_label, suffix in zip(task_info['runs'], task_info['suffixes']):
                    for mod in self.FUNCTIONAL_MODULES + ["Final"]:
                        frontend_key = f"{mod}{suffix}"
                        row_data[f"{mod}_{run_label}_r"] = ratings.get(frontend_key, "NA")
                        row_data[f"{mod}_{run_label}_c"] = notes.get(frontend_key, "")

                # Save per-task CSV
                name_parts = []
                if session is not None:
                    name_parts.append(f"ses-{session}")
                name_parts.append(task_name)
                name_parts += [f"{k}-{v}" for k, v in task_info['extras'].items()]
                csv_prefix = "_".join(name_parts)
                csv_file = self.output_dir / f"sub-{participant_id}_{csv_prefix}.csv"

                with csv_file.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=list(row_data.keys()))
                    writer.writeheader()
                    writer.writerow(row_data)

                # Collect for combined CSV
                for key, value in row_data.items():
                    if key != "ID":
                        all_combined_data[f"{csv_prefix}_{key}"] = value
            
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
    
    def run_app_and_open_browsers(self, port: int = None, open_browser: bool = True):
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
        
        base_url = f"http://localhost:{port}"
        links = [self.gate.link(base_url, f"/{subject_id}") for subject_id in self.subjects]
        self.logger.info("Open these links to rate (the token is valid for this session only):")
        for link in links:
            self.logger.info(f"  {link}")

        # Without a display, webbrowser may fall back to a console browser that takes over the terminal
        headless = sys.platform.startswith("linux") and not (
            os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        if open_browser and not headless:
            for link in links:
                webbrowser.open(link)
        
        self.logger.info("Server is running. Press Ctrl+C to stop.")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Shutting down server...")