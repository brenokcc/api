var reloadable = null;

document.addEventListener("DOMContentLoaded", function(e) {

});

function scrollIntoViewWithOffset(element){
  window.scrollTo({
    behavior: 'smooth',
    top:
      element.getBoundingClientRect().top -
      document.body.getBoundingClientRect().top
  })
}

function request(method, url, callback, data){
    const token = localStorage.getItem('token');
    var headers = {'Accept': 'application/json'}
    if(token) headers['Authorization'] = 'Token '+token;
    url = url.replace(document.location.origin, '');
    if(url.indexOf(API_URL) == -1) url = API_URL + url;
    var params = {method: method, headers: new Headers(headers)};
    if(data) params['body'] = data;
    var httpResponse = null;
    fetch(url, params).then(
        function (response){
            httpResponse = response;
            return response.text()
        }
    ).then(
        text => {
            var data = JSON.parse(text||'{}');
            if(data.redirect) document.location.href = data.redirect;
            callback(data, httpResponse);
        }
    );
}

function closeDialogs(){
    var dialogs = document.getElementsByTagName('dialog');
    for(var i=0; i<dialogs.length; i++){
        var dialog = dialogs[i];
        dialog.close();
        dialog.classList.remove('opened');
        dialog.remove();
        $('.layer').hide();
        if(window.reloader) window.reloader();
    }
}

function initialize(element){
    if(!element) element = document;
    var message = getCookie('message');
    if(message){
        showMessage(message);
        setCookie('message', null);
    }
    $(element).find("a.modal").each( function(i, link) {
        link.addEventListener("click", function(){
            event.preventDefault();
            openDialog(link.href);
        });
    });
    $(element).find("input[type=file]").each(function(i, input) {
        input.addEventListener('change', function (e) {
            if (e.target.files) {
                let file = e.target.files[0];
                if(['png', 'jpeg', 'jpg', 'gif'].indexOf(file.name.toLowerCase().split('.').slice(-1)[0])<0) return;
                var reader = new FileReader();
                reader.onload = function (e) {
                    const MAX_WIDTH = 400;
                    var img = document.createElement("img");
                    img.id = input.id+'img';
                    img.style.width = 200;
                    img.style.display = 'block';
                    img.style.marginLeft = 300;
                    img.onload = function (event) {
                        const ratio = MAX_WIDTH/img.width;
                        var canvas = document.createElement("canvas");
                        const ctx = canvas.getContext("2d");
                        canvas.height = canvas.width * (img.height / img.width);
                        const oc = document.createElement('canvas');
                        const octx = oc.getContext('2d');
                        oc.width = img.width * ratio;
                        oc.height = img.height * ratio;
                        octx.drawImage(img, 0, 0, oc.width, oc.height);
                        ctx.drawImage(oc, 0, 0, oc.width * ratio, oc.height * ratio, 0, 0, canvas.width, canvas.height);
                        oc.toBlob(function(blob){
                            input.blob = blob;
                        });
                        input.parentNode.appendChild(img);

                    }
                    img.src = e.target.result;
                }
                reader.readAsDataURL(file);
            }
        });
    });
    $(element).find(".async").each(function(i, div) {
        fetch(div.dataset.url).then(
            function(response){
                response.text().then(
                    function(html){
                        var parser = new DOMParser();
                        var doc = parser.parseFromString(html, 'text/html');
                        var div2 = doc.getElementById(div.id)
                        div.innerHTML = div2.innerHTML;
                    }
                )
            }
        );
    });
}

function copyToClipboard(value){
    navigator.clipboard.writeText(value);
    showMessage('"'+value+'" copiado para a área de transferência!');
}

function setInnerHTML(elm, html) {
  elm.innerHTML = html;

  Array.from(elm.querySelectorAll("script"))
    .forEach( oldScriptEl => {
      const newScriptEl = document.createElement("script");

      Array.from(oldScriptEl.attributes).forEach( attr => {
        newScriptEl.setAttribute(attr.name, attr.value)
      });

      const scriptText = document.createTextNode(oldScriptEl.innerHTML);
      newScriptEl.appendChild(scriptText);

      oldScriptEl.parentNode.replaceChild(newScriptEl, oldScriptEl);
  });
}
function displayLayer(display){
    document.querySelector('.layer').style.display = display;
}
function setCookie(cname, cvalue, exdays) {
  const d = new Date();
  if(cvalue==null) exdays = 0;
  d.setTime(d.getTime() + (exdays*24*60*60*1000));
  let expires = "expires="+ d.toUTCString();
  document.cookie = cname + "=" + cvalue + ";" + expires + ";path=/";
}
function getCookie(cname) {
  let name = cname + "=";
  let ca = document.cookie.split(';');
  for(let i = 0; i < ca.length; i++) {
    let c = ca[i];
    while (c.charAt(0) == ' ') {
      c = c.substring(1);
    }
    if (c.indexOf(name) == 0) {
      return c.substring(name.length, c.length);
    }
  }
  return "";
}
function hideMessage(){
    var feedback = document.querySelector(".notification");
    if(feedback) feedback.style.display='none';
}
function showMessage(text, style){
    hideMessage();
    var feedback = document.querySelector(".notification");
    feedback.innerHTML = text;
    feedback.classList.remove('danger');
    feedback.classList.remove('success');
    feedback.classList.remove('warning');
    feedback.classList.remove('info');
    feedback.classList.add(style||'success');
    feedback.style.display='block';
    setTimeout(function(){feedback.style.display='none';}, 5000);
}

function showTask(key, callback){
    fetch('/api/v1/task_progress/?key='+key).then(
        function(response){
            response.text().then(
                function(text){
                    var btn = document.querySelector(".btn.submit")
                    btn.innerHTML = "Aguarde... ("+text+"%)";
                    if(text == "100"){
                        callback();
                    } else if(text != ""){
                        setTimeout(function(){showTask(key, callback)}, 3000)
                    }
                }
            )
        }
    );
}

function formHide(id){
    if(id){
        var fieldset = document.querySelector(".form-fieldset."+id);
        if(fieldset) fieldset.style.display = 'none';
        var field = document.querySelector(".form-group."+id);
        if(field) field.style.display = 'none';
    }
}
function formShow(id){
    if(id){
        var fieldset = document.querySelector(".form-fieldset."+id);
        if(fieldset) fieldset.style.display = 'block';
        var field = document.querySelector(".form-group."+id);
        if(field) field.style.display = 'block';
    }
}
function formValue(id, value){
    var group = document.querySelector(".form-group."+id);
    var widget = group.querySelector('*[name="'+id+'"]');
    if(widget.tagName == "INPUT"){
        widget.value = value;
    } else {
        if(widget.tagName == "SELECT"){
            if(widget.style.display=="none"){
                setAcValue(widget.id, value.id, value.text);
            } else {
                for (var i = 0; i < widget.options.length; i++) {
                    if (widget.options[i].value == value) {
                        widget.selectedIndex = i;
                        break;
                    }
                }
            }
        }
    }
}
function formControl(controls){
    if(controls){
        for (var i = 0; i < controls.hide.length; i++) formHide(controls.hide[i]);
        for (var i = 0; i < controls.show.length; i++) formShow(controls.show[i]);
        for (var k in controls.set) formValue(k, controls.set[k]);
    }
}
function formWatch(watch){
    if(watch){
        for (var i = 0; i < watch.length; i++){
            var id = watch[i];
            var group = document.querySelector(".form-group."+id);
            var widgets = group.querySelectorAll('*[name="'+id+'"]');
            widgets.forEach(function( widget ) {
                widget.addEventListener("change", function (e) {
                    var form = widget.closest('form');
                    var data = new FormData(form);
                    request('POST', form.action+'?on_change='+this.name, formControl, data);
                });
            });
        }
    }
}

