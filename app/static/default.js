function closeModal() {
	var container = document.getElementById("response-div")
	var backdrop = document.getElementById("modal-backdrop")
	var modal = document.getElementById("modal")

	modal.classList.remove("show")
	backdrop.classList.remove("show")

	setTimeout(function() {
		container.removeChild(backdrop)
		container.removeChild(modal)
	}, 200)
}

document.addEventListener('htmx:afterSwap', function(event){
    console.log(event)
    //if (event.detail.requestConfig.elt.classList.contains('btn-primary')) return;
    if (event.detail.pathInfo.requestPath.startsWith("/api/expirePassword") ||
        event.detail.pathInfo.requestPath.startsWith("/api/disableMachine") ||
        event.detail.pathInfo.requestPath.startsWith("/api/disableUnenrolledMachines") ) {
        var toasts = document.getElementById("toast-div");
        //show latest toast
        var toast = new bootstrap.Toast(toasts.children[toasts.childElementCount-1].children[0]);
        toast.show();
    }
    
})

document.addEventListener("closeModal", function(evt){
    closeModal()
})

document.addEventListener('DOMContentLoaded', function () {

    function setActiveNav() {
        var current = location.href.split('?')[0];
        if (current === "") return;
        var menuItems = document.querySelectorAll('.nav-link');
        for (var i = 0, len = menuItems.length; i < len; i++) {
            if (menuItems[i].href === current) {
                menuItems[i].className += " active";
            }
        }
    };

    setActiveNav();

});
