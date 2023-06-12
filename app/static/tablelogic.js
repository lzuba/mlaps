
function searchTable() {
	var text = document.getElementById("search-input").value;
	var rows = document.getElementsByTagName("table")[0].rows;
	//console.log(rows.length)
	for (var i = 1; i < rows.length; i++) {
		var row = rows[i];
		var found = false;
		for (var j = 0; j < (rows[i].cells.length - 1); j++) {
			if (found){ break; } 
			var cell = row.cells[j];
			//console.log(cell);
			var content = cell.innerHTML;
			//console.log(content);
			var cfound = content.search(text);
			//console.log(cfound);
			if (cfound >= 0) {
				// match found
				found = true;
			}
		}

		if (found) {
			row.style.display = null;
		} else {
			row.style.display = "none";
		}

	}

}