$chrome = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$dir = "C:\Users\Hello\propertydata\site"
$tmp = "C:\Users\Hello\AppData\Local\Temp\crshot1"
$src = "$dir\index.html"
$fileurl = "file:///" + ($src -replace '\','/')
$out = "$dir\_render_full.png"
$cargs = @("--headless=new","--disable-gpu","--no-sandbox","--hide-scrollbars",
  "--user-data-dir=$tmp","--force-device-scale-factor=1","--window-size=1512,8200",
  "--virtual-time-budget=3500","--screenshot=$out",$fileurl)
Start-Process -FilePath $chrome -ArgumentList $cargs -NoNewWindow -Wait -PassThru | Out-Null
Write-Output "done full"
