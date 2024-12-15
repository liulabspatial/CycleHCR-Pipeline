arg = getArgument();
print("Stitching");

args = split(arg, ";;");

print(args[0]);
print(args[1]);
print(args[2]);
print(args[3]);
print(args[4]);

call("ij.Prefs.setThreads", args[4]);

run("Calculate pairwise shifts ...", args[0]);
run("Filter pairwise shifts ...", args[1]);
run("Optimize globally and apply shifts ...", args[2]);
run("ICP Refinement ...", args[3]);

print("STITCH_IJM_DONE")
eval("script", "System.exit(0);");
run("Quit");