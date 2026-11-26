# Opening the pages

`fmriqc rating fmriprep` and `fmriqc dashboard` start a small web server and print a link in the terminal, for example:

```
http://localhost:5003/0030?token=Xk3v9QpL2mR7tYwZ8aBcD1eF4gH6jK0n
```

Open that link in your browser. On your own computer, `fmriqc rating fmriprep` opens the rating pages by itself. The server runs until you press Ctrl+C in the terminal, so keep the terminal open while you work.

Every start prints a new link. If a page says "Access denied", use the link printed most recently.

## On an HPC cluster

The server runs on the cluster, and your browser runs on your own computer, so the browser needs a tunnel to reach it.

1. Start the command on the cluster. For `fmriqc rating fmriprep`, add `--no-browser`, which only prints the links.
2. Note the port number in the link, `5003` in the example above.
3. On your own computer, open a new terminal and run, with your user name and the cluster's address:

   ```bash
   ssh -N -L 5003:127.0.0.1:5003 user@hpc.example.edu
   ```

   This command prints nothing and keeps running. Leave that terminal open.
4. Open the printed link in your browser.

If the server runs on a compute node (for example `node123` in an `srun` or `salloc` session), go through the login node to that node:

```bash
ssh -N -L 5003:127.0.0.1:5003 -J user@hpc.example.edu user@node123
```

`fmriqc rating afni` is different: it opens the APQC pages with AFNI's own `open_apqc.py`, so follow AFNI's instructions for viewing APQC remotely (see [Rating AFNI output](rating-afni.md)).

## The token

The token in the link keeps other users on the same machine, such as an HPC login node, out of your pages and ratings. After the first visit the browser keeps it in a cookie, so you can move between pages without the token in the address.

If you forward to a different local port (`-L 8888:127.0.0.1:5003`), change the port in the link and keep the token.

`fmriqc dashboard --host` binds the dashboard to an address that other machines can reach. The token is then the only protection, so share the link only with people who should see the data. With `--host 0.0.0.0` the printed link uses the machine's hostname, and `--debug` is refused.
