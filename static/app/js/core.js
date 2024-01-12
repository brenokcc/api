var reloadable = null;
var messageTimeout = null

const applicationServerPublicKey = 'BLoLJSopQbe04v_zpegJmayhH2Px0EGzrFIlM0OedSOTYsMpO5YGmHOxbpPXdM09ttIuDaDTI86uC85JXZPpEtA';
let swRegistration = null;

function urlB64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/\-/g, '+').replace(/_/g, '/');
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}

function pushSubscription(){
    if ('serviceWorker' in navigator && 'PushManager' in window) {
        //console.log('Service Worker and Push is supported');
        navigator.serviceWorker.register('/api/static/app/js/sw.js')
            .then(function (swRegistration) {
                console.log('Service Worker is registered');
                const applicationServerKey = urlB64ToUint8Array(applicationServerPublicKey);
                swRegistration.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: applicationServerKey
                }).then(function (subscription) {
                    console.log(subscription);
                    subscriptionJson = JSON.stringify(subscription);
                    console.log(subscriptionJson);
                    if (subscription) {
                        alert('Notificação ativida com sucesso.');
                    } else {
                        alert('Problema ao ativar notificações.');
                        return;
                    }
                    var data = new FormData();
                    data.append('subscription', subscriptionJson);
                    request('POST', '/api/push_subscription/', function(data){
                        console.log(data);
                     }, data);
                }).catch(function (err) {
                    alert('Problema ao tentar ativar notificações.');
                    console.log('Failed to subscribe the user: ', err);
                });
            })
            .catch(function (error) {
                alert('Erro');
                console.error('Service Worker Error', error);
            });
    } else {
        alert('Push messaging is not supported');
    }
}

document.addEventListener("DOMContentLoaded", function(e) {

});

function animate(){
	if($('.loaderValue').width()>0 && $('.loaderContainer').width()>$('.loaderValue').width()){
		$('.loaderValue').width($('.loaderValue').width()+$('.loaderContainer').width()/100);
		setTimeout(animate, 25);
	} else {
		$('.loaderValue').width(0);
	}
}
function startAnimation(){
    if($('.loaderValue').width()==0){
        $('.loaderValue').width(1);
	    animate();
	}
}
function stopAnimation(){
	$('.loaderValue').width(0);
}

function scrollIntoViewWithOffset(element){
  window.scrollTo({
    behavior: 'smooth',
    top:
      element.getBoundingClientRect().top -
      document.body.getBoundingClientRect().top
  })
}

function request(method, url, callback, data){
    startAnimation()
    const token = localStorage.getItem('token');
    var headers = {'Accept': 'application/json'}
    if(token && url.indexOf('/logout/')==-1) headers['Authorization'] = 'Token '+token;
    url = url.replace(document.location.origin, '');
    url = url.replace('/app/', '/api/')
    if(url.indexOf(API_URL) == -1) url = API_URL + url;
    var params = {method: method, headers: new Headers(headers), ajax: 1};
    if(data) params['body'] = data;
    var httpResponse = null;
    var contentType = null;
    fetch(url, params).then(
        function (response){
            httpResponse = response;
            contentType = httpResponse.headers.get('Content-Type');
            if(contentType=='application/json') return response.text();
            else if(contentType.indexOf('text')<0 || contentType.indexOf('csv')>=0) return response.arrayBuffer();
            else response.text()
        }
    ).then(result => {
            stopAnimation();
            if(contentType=='application/json'){
                var data = JSON.parse(result||'{}');
                if(data.token){
                    if(document.location.pathname=='/app/login/'){
                        localStorage.removeItem("application");
                    }
                    localStorage.setItem('token', data.token);
                    localStorage.setItem('user', data.user.username);
                }
                if(data.redirect){
                    if(data.message) setCookie('message', data.message);
                    document.location.href = data.redirect.replace('/api/', '/app/');
                } else {
                    if(data.message && !data.task)  showMessage(data.message);
                    if(callback) callback(data, httpResponse);
                }
            } else if(contentType.indexOf('text')<0 || contentType.indexOf('csv')>=0){
                var file = window.URL.createObjectURL(new Blob( [ new Uint8Array(result) ], { type: contentType }));
                var a = document.createElement("a");
                a.href = file;
                if (contentType.indexOf('excel') >= 0) a.download = 'Download.xls';
                else if (contentType.indexOf('pdf') >= 0) a.download = 'Download.pdf';
                else if (contentType.indexOf('zip') >= 0) a.download = 'Download.zip';
                else if (contentType.indexOf('json') >= 0) a.download = 'Download.json';
                else if (contentType.indexOf('csv') >= 0) a.download = 'Download.csv';
                else if (contentType.indexOf('png') >= 0) a.download = 'Download.png';
                document.body.appendChild(a);
                a.click();
                if(callback) callback({}, httpResponse);
            } else {
                if(callback) callback(result, httpResponse);
            }
        }
    );
}

function closeDialogs(message){
    if(message!=null) showMessage(message);
    var dialogs = document.getElementsByTagName('dialog');
    for(var i=0; i<dialogs.length; i++){
        if(i==dialogs.length-1){
            var dialog = dialogs[i];
            dialog.close();
            dialog.classList.remove('opened');
            dialog.remove();
            if(i==0){
                $('.layer').hide();
                if(window.reloader) window.reloader();
            } else {
                dialogs[i-1].style.display = "block";
            }
        }
    }
}

function initialize(element){
    if(!element) element = document;
    var message = getCookie('message');
    if(message){
        showMessage(message);
        setCookie('message', null);
    }
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
    if(messageTimeout){
        clearTimeout(messageTimeout);
        messageTimeout = null;
    }
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
    messageTimeout = setTimeout(function(){feedback.style.display='none';}, 5000);
}
