var timeout = null;
function resizeDialog(height){
    if($('dialog:visible').length){
        $('dialog:visible').css(
            'height', (parseFloat($('dialog:visible').css('height').toString().replace('px', ''))+height).toString()+'px'
        );
    }
}
function setAcValue(name, value, label){
    var select = document.getElementById(name);
    var input = document.getElementById(name+'autocomplete');
    var clearer = input.parentNode.querySelector('.clearer');
    if(value!=null){
        var option = document.createElement('option');
        option.value = value;
        option.selected = true;
        option.innerHTML = label;
        if(!select.multiple) select.innerHTML = ''
        if(value) select.add(option);
        if(select.multiple) createBoxes(name);
        else input.value = label;
        clearer.classList.remove('fa-angle-down');
        if(!select.multiple) clearer.classList.add('fa-x');
    } else {
        input.value = "";
        if(!select.multiple) select.innerHTML = "";
        clearer.classList.add('fa-angle-down');
        clearer.classList.remove('fa-x');
    }
}
function escapeHtml(unsafe){
    return unsafe
         .replace(/&/g, "&amp;")
         .replace(/</g, "&lt;")
         .replace(/>/g, "&gt;")
         .replace(/"/g, "&quot;")
         .replace(/'/g, "&#039;");
}
function createBoxes(name){
    var select = document.getElementById(name)
    var boxes = document.getElementById(name+"boxes");
    boxes.innerHTML = '';
    for(var i=0; i<select.options.length; i++){
        var option = select.options[i];
        if(option.value){
            var box = document.createElement("DIV");
            box.classList.add("autocomplete-box");
            var close = document.createElement("SPAN");
            var value = document.createElement("SPAN");
            close.innerHTML = '<i class="fa-solid fa-trash"/>';
            close.id = i;
            close.style.cursor = 'pointer';
            value.innerHTML = option.innerHTML;
            box.appendChild(close);
            box.appendChild(value);
            boxes.appendChild(box);
            close.addEventListener("click", function(e) {
                this.parentNode.remove(this);
                select.options.remove(this.id);
                createBoxes(name);
            });
        }
    }
}
function normalize(text){
    return text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace('_', '').replace('-', '').toLowerCase();
}
function autocomplete(name, placeholder, multiple, url, callback, onselect) {
 var select = document.getElementById(name);
 var inp = document.getElementById(name+'autocomplete');
 if(inp==null){
    inp = document.createElement('INPUT');
    inp.id = name+'autocomplete';
    inp.autocomplete = 'off';
    inp.type = 'text';
    inp.name = name+'autocomplete';
    inp.dataset.label = normalize(placeholder);
    inp.onclick = "this.select()";
    inp.placeholder = placeholder;
    inp.title = name;
    inp.classList.add("form-control");
    select.parentNode.appendChild(inp);
 }

  if(multiple) createBoxes(name);
  inp.addEventListener('focus', function(e) {
    this.select();
  });
  ['input', 'click'].forEach(function(type){
      inp.addEventListener(type, function(e) {
        function search(){
            var a, b, i, val = inp.value;
            if(url == null) url = document.location.pathname;
            var tokens = url.split('?');
            url = tokens[0];
            if(tokens.length>1) var usp = new URLSearchParams(tokens[1]);
            else var usp = new URLSearchParams();
            usp.set('choices_field', name.split('__0.')[0]);
            usp.set('choices_search', val);
            var form = inp.closest('form');
            if(form){
                var selects = form.querySelectorAll('select');
                for(var j=0; j<selects.length; j++){
                    usp.delete(selects[j].name);
                    if(selects[j].selectedIndex>=0){
                        if(selects[j].options[selects[j].selectedIndex].value){
                            usp.set(selects[j].name, selects[j].options[selects[j].selectedIndex].value);
                        }
                    }
                }
                var radios = form.querySelectorAll('input[type="radio"]');
                for(var j=0; j<radios.length; j++) usp.delete(radios[j].name);
                for(var j=0; j<radios.length; j++){
                    if(radios[j].checked) usp.set(radios[j].name, radios[j].value.toString());
                }
            }
            url = url+'?'+usp.toString();
            request('GET', url, function(data){
                  /*close any already open lists of autocompleted values*/
                  closeAllLists();
                  currentFocus = -1;
                  /*create a DIV element that will contain the items (values):*/
                  a = document.createElement("DIV");
                  a.setAttribute("id", inp.id + "autocomplete-list");
                  a.setAttribute("class", "autocomplete-items");
                  /*append the DIV element as a child of the autocomplete container:*/
                  inp.parentNode.appendChild(a);
                  /*for each item in the array...*/
                  var empty = document.createElement("DIV");
                  empty.classList.add("autocomplete-item");
                  empty.innerHTML = 'Nenhum registro encontrado';
                  for (i = 0; i < data.length; i++) {
                    if (true) {
                      if(callback) data[i] = callback(data[i]);
                      /*create a DIV element for each matching element:*/
                      b = document.createElement("DIV");
                      b.classList.add("autocomplete-item");
                      b.dataset.label = normalize(data[i].text);
                      /*make the matching letters bold:*/
                      b.innerHTML = escapeHtml(data[i].text);
                      /*insert a input field that will hold the current array item's value:*/
                      b.innerHTML += "<input class='" + data[i].id + "' type='hidden' value='" + data[i].text + "'>";
                      /*execute a function when someone clicks on the item value (DIV element):*/
                          b.addEventListener("click", function(e) {
                          /*insert the value for the autocomplete text field:*/
                            if(multiple){
                                inp.value = "";
                            } else {
                                inp.value = this.getElementsByTagName("input")[0].value;
                                var length = document.getElementById(name).options.length;
                                for(var j=0; j<length; j++){
                                    document.getElementById(name).options.remove(0);
                                }
                            }
                            if(onselect){
                                onselect(this.getElementsByTagName("input")[0].className);
                            } else {
                                var value = this.getElementsByTagName("input")[0].className;
                                var label = this.getElementsByTagName("input")[0].value;
                                setAcValue(name, value, label);
                            }
                          /*close the list of autocompleted values,
                          (or any other open lists of autocompleted values:*/
                          closeAllLists();
                      });
                      a.appendChild(b);
                    }
                  }
                  if(!a.innerHTML) a.appendChild(empty);
            });
        }
        if(timeout) clearTimeout(timeout);
        timeout = setTimeout(search, 500);
      });
  });
  inp.addEventListener("blur", function(e) {
    if(!this.value && !multiple){
        var select = document.getElementById(name);
        var option = document.createElement('option');
        select.innerHTML = '';
        option.innerHTML = '--------';
        option.value = '';
        select.add(option);
    }
  });
  /*execute a function presses a key on the keyboard:*/
  inp.addEventListener("keydown", function(e) {
      var x = document.getElementById(this.id + "autocomplete-list");
      if (x) x = x.getElementsByTagName("div");
      if (e.keyCode == 40) {
        /*If the arrow DOWN key is pressed,
        increase the currentFocus variable:*/
        currentFocus++;
        /*and and make the current item more visible:*/
        addActive(x);
      } else if (e.keyCode == 38) { //up
        /*If the arrow UP key is pressed,
        decrease the currentFocus variable:*/
        currentFocus--;
        /*and and make the current item more visible:*/
        addActive(x);
      } else if (e.keyCode == 13) {
        /*If the ENTER key is pressed, prevent the form from being submitted,*/
        e.preventDefault();
        if (currentFocus > -1) {
          /*and simulate a click on the "active" item:*/
          if (x) x[currentFocus].click();
        }
      }
  });
  function addActive(x) {
    /*a function to classify an item as "active":*/
    if (!x) return false;
    /*start by removing the "active" class on all items:*/
    removeActive(x);
    if (currentFocus >= x.length) currentFocus = 0;
    if (currentFocus < 0) currentFocus = (x.length - 1);
    /*add class "autocomplete-active":*/
    x[currentFocus].classList.add("autocomplete-active");
  }
  function removeActive(x) {
    /*a function to remove the "active" class from all autocomplete items:*/
    for (var i = 0; i < x.length; i++) {
      x[i].classList.remove("autocomplete-active");
    }
  }
  function closeAllLists(elmnt) {
    /*close all autocomplete lists in the document,
    except the one passed as an argument:*/
    var x = document.getElementsByClassName("autocomplete-items");
    for (var i = 0; i < x.length; i++) {
      if (elmnt != x[i] && elmnt != inp) {
      x[i].parentNode.removeChild(x[i]);
    }
  }
}
/*execute a function when someone clicks in the document:*/
document.addEventListener("click", function (e) {
    closeAllLists(e.target);
});
}