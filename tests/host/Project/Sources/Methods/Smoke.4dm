//%attributes = {"invisible":true}
var $ignored : Integer
var $parameter; $name; $target : Text
var $request; $result; $report : Object
var $tool : cs.TemplateCLI.Greeting
var $requestFile; $statusFile : 4D.File
var $cases : Collection
$ignored:=Get database parameter(User param value; $parameter)
If (Is Windows)
	$requestFile:=File($parameter; fk platform path)
Else
	$requestFile:=File($parameter; fk posix path)
End if
$request:=JSON Parse($requestFile.getText())
If (Is Windows)
	$statusFile:=File($request.status; fk platform path)
Else
	$statusFile:=File($request.status; fk posix path)
End if
$statusFile.setText("{\"success\":false,\"phase\":\"starting\"}")
$target:="macOS-universal"
If (Is Windows)
	$target:="Windows-x64"
End if
$tool:=cs.TemplateCLI.Greeting.new($target)
$cases:=New collection("world"; "path with spaces"; "quote \" and \\ slash"; "line\nbreak"; "日本語"; "$() ; & % !")
$report:=New object("success"; True; "cases"; New collection)
$report.compiled:=$tool._cli.compiled
If ($request.expectCompiled & Not($report.compiled))
	$report.success:=False
End if
For each ($name; $cases)
	$result:=$tool.greet($name)
	$report.cases.push($result)
	If (Not($result.ok))
		$report.success:=False
	Else
		If ($result.value.message#("Hello, "+$name+"!"))
			$report.success:=False
		End if
	End if
End for each
$result:=$tool.greet("")
$report.invalid:=$result
If ($result.ok | ($result.exitCode#2))
	$report.success:=False
End if
$result:=$tool.version()
$report.version:=$result
If (Not($result.ok))
	$report.success:=False
Else
	If ($result.value.version#"0.1.0")
		$report.success:=False
	End if
End if
$result:=cs.TemplateCLI._CLI.new("missing-cli"; $target).execute(New collection("--version"))
$report.missing:=$result
If ($result.error.code#"missing_executable")
	$report.success:=False
End if
$result:=cs.TemplateCLI.Greeting.new("unsupported-arm-target").version()
$report.unsupported:=$result
If ($result.error.code#"unsupported_architecture")
	$report.success:=False
End if
$result:=cs.TemplateCLI._Process.new().execute($requestFile; New collection)
$report.launch:=$result
If ($result.error.code#"launch_failed")
	$report.success:=False
End if
$result:=$tool._decode(New object("ok"; True; "stdout"; "not json"); "message")
$report.protocol:=$result
If ($result.error.code#"invalid_protocol")
	$report.success:=False
End if
$result:=cs.TemplateCLI._CLI.new("component-cli"; $target).execute(New collection("greet"; "--name"; $requestFile))
$report.fileArgument:=$result
If (Not($result.ok))
	$report.success:=False
Else
	If (JSON Parse($result.stdout).message#("Hello, "+$parameter+"!"))
		$report.success:=False
	End if
End if
$statusFile.setText(JSON Stringify($report))
QUIT 4D
