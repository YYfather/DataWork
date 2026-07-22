// ── Avatar：裁剪 + 上传 ──
(function(){
  var avatarImg=document.getElementById('avatarImg');
  var avatarInput=document.getElementById('avatarInput');
  var avatarContainer=document.getElementById('avatarContainer');
  var cropOverlay=document.getElementById('cropOverlay');
  var cropImage=document.getElementById('cropImage');
  var cropMask=document.getElementById('cropMask');
  var cropZoom=document.getElementById('cropZoom');
  var cropZoomLabel=document.getElementById('cropZoomLabel');
  var cropPreviewImg=document.getElementById('cropPreviewImg');
  var cropConfirm=document.getElementById('cropConfirm');
  var cropCancel=document.getElementById('cropCancel');
  var cropState={img:null,scale:1,dx:0,dy:0};
  var isDragging=false,dragStartX=0,dragStartY=0,dragOrigDX=0,dragOrigDY=0;

  // Load avatar
  function loadAvatar(){
    var t=localStorage.getItem('hp_avatar_ts');
    avatarImg.src='avatar.jpg'+(t?'?'+t:'');
  }
  loadAvatar();

  // Click → file picker (with dblclick guard)
  var _clickTimer;
  avatarContainer.addEventListener('click',function(){
    if(_clickTimer){clearTimeout(_clickTimer);_clickTimer=null;return;}
    _clickTimer=setTimeout(function(){_clickTimer=null;avatarInput.click();},280);
  });
  avatarContainer.addEventListener('dblclick',function(e){
    e.stopPropagation();
    if(confirm('恢复默认头像？')){
      localStorage.removeItem('hp_avatar_ts');
      avatarImg.src='avatar.jpg?'+Date.now();
      showToast('已恢复默认头像');
    }
  });
  avatarInput.addEventListener('change',function(e){
    var file=e.target.files[0];if(!file)return;
    var reader=new FileReader();
    reader.onload=function(ev){
      var img=new Image();
      img.onload=function(){openCrop(img);};
      img.src=ev.target.result;
    };
    reader.readAsDataURL(file);
    avatarInput.value='';
  });

  function openCrop(img){
    cropState={img:img,scale:1,dx:0,dy:0};
    cropImage.src=img.src;
    resetCropTransform();
    cropOverlay.style.display='flex';
    cropConfirm.disabled=false;
    updatePreview();
  }
  function resetCropTransform(){
    var maskSize=280;
    var img=cropState.img;
    var scale=Math.max(maskSize/img.width,maskSize/img.height);
    cropState.scale=scale;
    cropZoom.value=scale;
    cropZoomLabel.textContent=scale.toFixed(1)+'x';
    cropState.dx=0;cropState.dy=0;
    applyCropTransform();
  }
  function applyCropTransform(){
    var s=cropState.scale;
    cropImage.style.transform='translate(calc(-50% + '+cropState.dx+'px), calc(-50% + '+cropState.dy+'px)) scale('+s+')';
    updatePreview();
  }
  function updatePreview(){
    var maskSize=280;
    var natW=cropState.img.naturalWidth;
    var natH=cropState.img.naturalHeight;
    var s=cropState.scale;
    var cx=natW/2 - cropState.dx/s;
    var cy=natH/2 - cropState.dy/s;
    var half=maskSize/2/s;
    var sx=Math.max(0,cx-half), sy=Math.max(0,cy-half);
    var sw=Math.min(natW-cx+half,cx+half)-sx;
    var sh=Math.min(natH-cy+half,cy+half)-sy;
    if(sw<=0||sh<=0) return;
    var p=document.createElement('canvas');
    p.width=p.height=72;
    var pc=p.getContext('2d');
    pc.drawImage(cropState.img,sx,sy,sw,sh,0,0,72,72);
    cropPreviewImg.src=p.toDataURL();
  }

  // Drag
  cropMask.addEventListener('mousedown',function(e){
    isDragging=true;
    dragStartX=e.clientX;dragStartY=e.clientY;
    dragOrigDX=cropState.dx;dragOrigDY=cropState.dy;
    e.preventDefault();
  });
  document.addEventListener('mousemove',function(e){
    if(!isDragging)return;
    cropState.dx=dragOrigDX+(e.clientX-dragStartX);
    cropState.dy=dragOrigDY+(e.clientY-dragStartY);
    applyCropTransform();
  });
  document.addEventListener('mouseup',function(){isDragging=false;});
  cropMask.addEventListener('touchstart',function(e){
    var t=e.touches[0];
    isDragging=true;
    dragStartX=t.clientX;dragStartY=t.clientY;
    dragOrigDX=cropState.dx;dragOrigDY=cropState.dy;
    e.preventDefault();
  },{passive:false});
  cropMask.addEventListener('touchmove',function(e){
    if(!isDragging)return;
    var t=e.touches[0];
    cropState.dx=dragOrigDX+(t.clientX-dragStartX);
    cropState.dy=dragOrigDY+(t.clientY-dragStartY);
    applyCropTransform();
    e.preventDefault();
  },{passive:false});
  cropMask.addEventListener('touchend',function(){isDragging=false;});

  // Zoom
  cropZoom.addEventListener('input',function(){
    cropState.scale=parseFloat(this.value);
    cropZoomLabel.textContent=cropState.scale.toFixed(1)+'x';
    applyCropTransform();
  });

  // Cancel
  cropCancel.onclick=function(){cropOverlay.style.display='none';};

  // Confirm & Upload
  cropConfirm.onclick=async function(){
    cropConfirm.disabled=true;
    cropConfirm.textContent='上传中...';
    var maskSize=280;
    var natW=cropState.img.naturalWidth;
    var natH=cropState.img.naturalHeight;
    var s=cropState.scale;
    var cx=natW/2 - cropState.dx/s;
    var cy=natH/2 - cropState.dy/s;
    var half=maskSize/2/s;
    var sx=Math.max(0,cx-half);
    var sy=Math.max(0,cy-half);
    var sw=Math.min(natW,cx+half)-sx;
    var sh=Math.min(natH,cy+half)-sy;
    var size=Math.min(sw,sh);
    var c=document.createElement('canvas');
    c.width=c.height=400;
    var ctx=c.getContext('2d');
    ctx.drawImage(cropState.img,sx,sy,size,size,0,0,400,400);
    var dataUrl=c.toDataURL('image/jpeg',0.92);
    try{
      var resp=await fetch('./api/upload-avatar.php',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({image:dataUrl})
      });
      var result=await resp.json();
      if(!result.ok) throw new Error(result.error);
      var ts=Date.now();
      localStorage.setItem('hp_avatar_ts',ts);
      avatarImg.src='avatar.jpg?'+ts;
      cropOverlay.style.display='none';
      showToast('头像已更新');
    }catch(e){
      showToast('上传失败: '+e.message);
      cropConfirm.disabled=false;
      cropConfirm.textContent='确认';
    }
  };
})();
