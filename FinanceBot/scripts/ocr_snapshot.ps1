param(
    [Parameter(Mandatory=$true)][string]$ImagePath,
    [Parameter(Mandatory=$true)][string]$OutputPath
)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null=[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$null=[Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$null=[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]

function Await($Task,$Type){
    $method=[System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {$_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'} |
        Select-Object -First 1
    $netTask=$method.MakeGenericMethod($Type).Invoke($null,@($Task))
    $netTask.Wait()
    return $netTask.Result
}

$resolved=(Resolve-Path -LiteralPath $ImagePath).Path
$file=Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($resolved)) ([Windows.Storage.StorageFile])
$stream=Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder=Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap=Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine=[Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if($null -eq $engine){ throw "Windows 中文 OCR 语言包不可用" }
$result=Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
$words=@()
$lines=@()
foreach($line in $result.Lines){
    $lineWords=@()
    foreach($word in $line.Words){
        $rect=$word.BoundingRect
        $item=[pscustomobject]@{
            text=$word.Text
            x=[double]$rect.X
            y=[double]$rect.Y
            width=[double]$rect.Width
            height=[double]$rect.Height
        }
        $words+=$item
        $lineWords+=$item
    }
    $lines+=[pscustomobject]@{ text=$line.Text; words=$lineWords }
}
$payload=[pscustomobject]@{
    image_path=$resolved
    text=$result.Text
    lines=$lines
    words=$words
}
$OutputPath=[System.IO.Path]::GetFullPath($OutputPath)
$json=$payload | ConvertTo-Json -Depth 6
[System.IO.File]::WriteAllText($OutputPath,$json,[System.Text.UTF8Encoding]::new($false))
Write-Output "OCR output: $OutputPath"
