// delete confirmation

var confLink = document.querySelectorAll(".ui-app-delete > .ui-link");

for (var i = 0; i < confLink.length; i++) {
  var cm = confLink.item(i);

  cm.addEventListener("click", function(e) {
    if (!confirm("Willste das wirklich löschen?")) e.preventDefault();
  })
}


// comment mechanics

var cmech = document.querySelectorAll(".comment-mech")

for (var i = 0; i < cmech.length; i++) {
    var cm = cmech.item(i);
    
    let ind = cm.querySelector(".comment-indicator");
    let frm = cm.querySelector(".comment-form");

    frm.style.display = "none";

    ind.addEventListener("click", function () {
	if (frm.style.display === "none") {
	    frm.style.display = "block";
	} else {
	    frm.style.display = "none";
	}
    }, false);
}

// stick navbar to the top, once the user scrolls down

var navOffsetTop;

window.onload = function () {


    var bd = document.querySelector("body");
    var nav = document.querySelector(".navbar");

    bd.classList.remove("nav-has-docked");
    navOffsetTop = nav.clientTop;

    var checkdocked = function () {
	if ( navOffsetTop < window.pageYOffset &&
	     !bd.classList.contains("has-docked-nav") ) {
	    bd.classList.add("has-docked-nav");
	}

	if ( navOffsetTop > window.pageYOffset &&
	     bd.classList.contains("has-docked-nav") ) {
	    bd.classList.remove("has-docked-nav");
	}	
    };

    window.addEventListener("scroll", checkdocked, false);
    window.addEventListener("resize", function () {
	bd.classList.remove("nav-has-docked");
	navOffsetTop = nav.getBoundingClientRect().top;
	checkdocked();
    }, false);
    
};
