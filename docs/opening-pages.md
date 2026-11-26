# Opening the pages

`fmriqc rating fmriprep` and `fmriqc dashboard` print a link in the terminal, for example:

```
http://localhost:5003/0030?token=Xk3v9QpL2mR7tYwZ8aBcD1eF4gH6jK0n
```

`fmriqc rating fmriprep` opens its pages in your browser by itself. For the dashboard, copy the link into your browser. Keep the terminal open while you work, and press Ctrl+C there when you are done.

If a page says "Access denied", use the link printed most recently.

## On an HPC cluster

Work in a remote desktop on the cluster, such as XDesktop or an Open OnDemand desktop:

1. Start a remote desktop session and open a terminal in it.
2. Load Firefox, and AFNI if you rate AFNI output:

   ```bash
   ml Firefox
   ml AFNI
   ```

   Module names differ between clusters; `module avail firefox` lists yours.
3. Run the `fmriqc` commands in that terminal. The pages open in Firefox on the remote desktop.

Without a remote desktop, add `--no-browser` to `fmriqc rating fmriprep`, run `ssh -N -L 5003:127.0.0.1:5003 user@hpc.example.edu` on your own computer (with the port from the link), and open the link in your own browser.

## The token

The token in the link keeps other users of the cluster out of your pages and ratings. After the first visit, your browser remembers it.

`fmriqc dashboard --host` lets other computers open the dashboard. Anyone with the link can then see the data, so share it only with people who should.
