// Global variables injected from backend template
const modulesByRun = window.modulesByRunJson;  // Array of module groups
const initialRatings = window.initialRatingsJson || {};  // Initial ratings
const initialNotes = window.initialNotesJson || {};  // Initial comments

// Make sure participantId is provided by the backend template
const participantId = window.participantId || "UNKNOWN";

// Rating icons and states
const icons = { "NA": "◻", "good": "+", "bad": "−", "other": "?" };
const ratingStates = ["NA", "good", "bad", "other"];
const ratings = { ...initialRatings };  // Copy initial ratings
const notes = { ...initialNotes };  // Copy initial notes

const indexInner = document.querySelector("#qc-rating-index .qc-inner");
const barInner = document.querySelector("#qc-rating-bar .qc-inner");

// Generate the index links (left-side module names)
modulesByRun.forEach(runModules => {
  runModules.forEach(mod => {
    const link = document.createElement("a");
    link.textContent = mod.name;
    link.href = "#" + mod.id;
    indexInner.appendChild(link);
    // Initialize all modules with "NA" if not already set
    if (!(mod.id in ratings)) ratings[mod.id] = "NA";
    if (!(mod.id in notes)) notes[mod.id] = "";
  });
});

// Update a single module's visual display according to its rating
function updateModuleDisplay(modEl, modId) {
  const state = ratings[modId] || "NA";
  modEl.classList.remove("good", "bad", "other");
  if (state === "good") modEl.classList.add("good");
  else if (state === "bad") modEl.classList.add("bad");
  else if (state === "other") modEl.classList.add("other");
  modEl.querySelector(".qc-icon").textContent = icons[state];
}

// Prompt user to input or update a comment
function promptNote(modId, modName) {
  const existingNote = notes[modId] || "";
  const newNote = prompt(`Input comment for "${modName}"`, existingNote);
  if (newNote !== null) {
    notes[modId] = newNote.trim();
    saveRatingsToServer();
  }
}

// Save current ratings and notes to backend via POST
function saveRatingsToServer() {
  fetch("/save_ratings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // Important: Must include "id" or backend will fail
    body: JSON.stringify({ ratings, notes, id: participantId }),
  })
  .then(res => res.json())
  .then(data => {
    if (data.status !== "success") {
      alert("Failed to save rating: " + (data.message || ""));
    }
  })
  .catch(err => {
    alert("Network error while saving rating");
    console.error(err);
  });
}

// Generate the rating modules and bind click events
modulesByRun.forEach(runModules => {
  const runGroupDiv = document.createElement("div");
  runGroupDiv.className = "qc-run-group";
  
  runModules.forEach(mod => {
    const modEl = document.createElement("div");
    modEl.className = "qc-module";
    
    // Add special styling for Final modules
    if (mod.name.startsWith("Final")) {
      modEl.classList.add("final-module");
    }
    
    modEl.innerHTML = `<span class="qc-icon">◻</span><span class="label">${mod.name}</span>`;

    // On click: Ctrl+Click = Add/Edit note; Click = cycle rating
    modEl.addEventListener("click", (e) => {
      if (e.ctrlKey) {
        promptNote(mod.id, mod.name);
      } else {
        let currentState = ratings[mod.id] || "NA";
        let index = ratingStates.indexOf(currentState);
        let nextState = ratingStates[(index + 1) % ratingStates.length];
        ratings[mod.id] = nextState;
        updateModuleDisplay(modEl, mod.id);
        saveRatingsToServer();
      }
    });

    updateModuleDisplay(modEl, mod.id);
    runGroupDiv.appendChild(modEl);
  });
  
  barInner.appendChild(runGroupDiv);
});

// Export ratings and notes as CSV file (keeps original combined format)
function exportCsv() {
  const allModules = Array.from(new Set(modulesByRun.flat().map(mod => mod.id)));

  let headers = ["ID"];
  allModules.forEach(id => {
    const safeName = id.replace(/\s+/g, "_");
    headers.push(`${safeName}_r`);
    headers.push(`${safeName}_c`);
  });

  let csv = headers.join(",") + "\n";

  let row = [participantId];
  allModules.forEach(id => {
    const rating = ratings[id] || "NA";
    const note = notes[id] || "";
    row.push(rating);
    row.push(`"${note.replace(/"/g, '""')}"`);
  });

  csv += row.join(",") + "\n";

  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${participantId}_ratings.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// Get references to both scrollable containers
const indexContainer = document.querySelector("#qc-rating-index");
const barContainer = document.querySelector("#qc-rating-bar");

// Flags to prevent infinite scroll loops
let isIndexScrolling = false;
let isBarScrolling = false;

// Synchronize scrolling from index to bar
indexContainer.addEventListener('scroll', function() {
    if (!isIndexScrolling) {
        isBarScrolling = true;
        barContainer.scrollLeft = indexContainer.scrollLeft;
        
        // Reset the flag after a short delay
        setTimeout(() => {
            isBarScrolling = false;
        }, 10);
    }
});

// Synchronize scrolling from bar to index
barContainer.addEventListener('scroll', function() {
    if (!isBarScrolling) {
        isIndexScrolling = true;
        indexContainer.scrollLeft = barContainer.scrollLeft;
        
        // Reset the flag after a short delay
        setTimeout(() => {
            isIndexScrolling = false;
        }, 10);
    }
});

// Add mouse wheel support for the index (since it has hidden scrollbar)
indexContainer.addEventListener('wheel', function(e) {
    // Prevent vertical scrolling, allow horizontal scrolling
    if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
        return; // Let normal horizontal scroll happen
    }
    
    // Convert vertical scroll to horizontal scroll
    e.preventDefault();
    const scrollAmount = e.deltaY * 0.5; // Adjust multiplier as needed
    indexContainer.scrollLeft += scrollAmount;
}, { passive: false });