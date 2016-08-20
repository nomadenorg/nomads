
// comment mechanics

var cmech = document.querySelectorAll(".comment-mech")

for (var i = 0; i < cmech.length; i++) {
    cm = cmech.item(i);
    
    var indi = cm.querySelector(".comment-indicator");
    var form = cm.querySelector(".comment-form");

    form.style.display = "none";

    indi.addEventListener("click", function () {
	if (form.style.display === "none") {
	    form.style.display = "block";
	} else {
	    form.style.display = "none";
	}
    }, false);
}

// navigation

var navOffsetTop;
var bd = document.querySelector("body");
var nav = document.querySelector(".navbar");

navOffsetTop = nav.getBoundingClientRect().top;

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

pageXOffset
