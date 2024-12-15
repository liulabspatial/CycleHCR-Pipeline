arg = getArgument();
print("Stitching");

args = split(arg, ";;");

print(args[0]);

run("Resave N5 Local", args[0]);
//run("As TIFF ...", args[1]);

eval("script", "System.exit(0);");
run("Quit");