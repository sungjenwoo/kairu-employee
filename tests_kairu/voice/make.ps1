# Makes the recorded test sounds in this folder from phrases.txt, with Windows' own voices (PowerShell 7 on Windows:
# Mark is one of Windows' newer voices, which Windows PowerShell 5.1 cannot use). The WAV files are committed, so the
# tests run on Linux and with no microphone; run this again only to change them:
#     pwsh -NoProfile -File tests_kairu\voice\make.ps1
Add-Type -AssemblyName System.Speech
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
foreach ($line in Get-Content -Encoding UTF8 (Join-Path $here "phrases.txt")) {
    if (-not $line.Trim() -or $line.StartsWith('#')) { continue }
    $name, $voice, $text = $line.Split('|', 3)
    $speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $speaker.SelectVoice($voice)
    $speaker.SetOutputToWaveFile((Join-Path $here "$name.wav"), $format)
    $speaker.SpeakSsml("<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>$text</speak>")
    $speaker.Dispose()
}
