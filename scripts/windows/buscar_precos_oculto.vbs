' buscar_precos_oculto.vbs - roda o buscar_precos.bat SEM abrir janela de terminal.
' E este arquivo que o Agendador de Tarefas chama: assim ninguem fecha a busca sem querer.
' (O 0 no fim do Run = janela escondida; True = espera a busca terminar.)
Set shell = CreateObject("WScript.Shell")
pasta = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
shell.Run "cmd /c """ & pasta & "\buscar_precos.bat""", 0, True
