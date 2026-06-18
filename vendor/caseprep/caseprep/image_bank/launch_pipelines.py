#!/usr/bin/env python3
"""Launch 2 parallel DeepSeek V3 labeling pipelines, one per API key."""
import subprocess, sys, os, time, json

# Read .env for DeepSeek API keys
env = {}
with open('/mnt/c/Users/Michael/Desktop/PAPERS/.env') as f:
    for line in f:
        line = line.strip().rstrip('\r')
        if not line or line.startswith('#'): continue
        if '=' in line:
            k, v = line.split('=', 1)
            if k in env:
                if not isinstance(env[k], list): env[k] = [env[k]]
                env[k].append(v)
            else:
                env[k] = v

ds_key0 = env['DEEPSEEK_API_KEY'][0] if isinstance(env['DEEPSEEK_API_KEY'], list) else env['DEEPSEEK_API_KEY']
ds_key1 = env['DEEPSEEK_API_KEY'][1] if isinstance(env['DEEPSEEK_API_KEY'], list) else env['DEEPSEEK_API_KEY']

# Pipeline 1 clusters (32,053 images)
p1_clusters = [
    "orbitozygomatic_anterior_base", "spine_congenital", "spine_deformity",
    "cranioplasty_reconstruction", "avm_vascular_malformation", "spine_interventional",
    "csf_diversion_shunts", "pediatric_craniosynostosis", "tumor_skull_base",
    "spine_oncology", "spine_anatomy_approaches", "subarachnoid_cisterns",
    "radiosurgery", "cavernous_sinus_middle_fossa", "intracranial_hemorrhage",
    "jugular_foramen_petroclival", "anterior_interhemispheric", "lumbar_degenerative",
    "spine_infection_inflammatory", "flow_diversion", "cerebrovascular_other",
    "intracranial_atherosclerosis", "white_matter_deep_nuclei", "ventricular_microsurgery",
    "retrosigmoid_cpa", "transsphenoidal_skull_base",
]

# Pipeline 2 clusters (31,994 images)
p2_clusters = [
    "cranial_fixation", "venous_interventional", "cervical_trauma",
    "icp_monitoring", "functional_epilepsy", "carotid_cervical_vascular",
    "cervical_degenerative", "endoscopic_cranial_approaches", "intraoperative_imaging",
    "posterior_circulation_microsurgery", "neurocritical_care", "cranial_nerves_cisternal",
    "aneurysm_sah", "temporal_limbic", "stereotactic_biopsy",
    "stroke_thrombectomy", "pediatric_neurointerventional", "spine_trauma",
    "pterional_approach", "cerebral_venous_anatomy", "moyamoya",
    "minimally_invasive_spine", "general_neurointerventional", "brainstem_cerebellar",
    "far_lateral_craniovertebral",
]

script_dir = os.path.dirname(os.path.abspath(__file__))
pipeline_script = os.path.join(script_dir, "label_pipeline.py")

def launch(name, api_key, api_type, clusters, workers=10):
    cluster_str = ",".join(clusters)
    cmd = [
        sys.executable, pipeline_script,
        "--api-key", api_key,
        "--api-type", api_type,
        "--clusters", cluster_str,
        "--workers", str(workers),
    ]
    logfile = open(f"pipeline_{name}.log", "w", buffering=1)
    
    proc = subprocess.Popen(
        cmd,
        stdout=logfile,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=script_dir,
    )
    print(f"  {name} started (PID {proc.pid}), logging to pipeline_{name}.log")
    return proc, logfile

print("Launching 2 parallel DeepSeek V3 labeling pipelines...")
print("=" * 60)

# Launch both
proc1, log1 = launch("p1", ds_key0, "deepseek", p1_clusters, workers=10)
proc2, log2 = launch("p2", ds_key1, "deepseek", p2_clusters, workers=10)

print("\nBoth pipelines running. Monitor with:")
print("  tail -f pipeline_p1.log")
print("  tail -f pipeline_p2.log")
print("\nProgress check:")
print("  sqlite3 bank.db 'SELECT COUNT(*) FROM labels WHERE model LIKE \"%deepseek%\";'")
print("  sqlite3 bank.db 'SELECT COUNT(*) FROM (SELECT fig_id FROM images EXCEPT SELECT fig_id FROM labels);'")

# Wait and monitor progress
start = time.time()
while True:
    time.sleep(30)
    ret1 = proc1.poll()
    ret2 = proc2.poll()
    elapsed = time.time() - start
    
    import sqlite3
    db = sqlite3.connect(os.path.join(script_dir, "bank.db"), timeout=5)
    cur = db.cursor()
    labeled = cur.execute("SELECT COUNT(*) FROM labels WHERE model LIKE '%deepseek%'").fetchone()[0]
    unlabeled = cur.execute("SELECT COUNT(*) FROM images i WHERE i.fig_id NOT IN (SELECT fig_id FROM labels) AND i.caption IS NOT NULL AND i.caption != ''").fetchone()[0]
    db.close()
    
    print(f"\n[{elapsed/60:.0f}m] Labeled: {labeled:,} | Remaining: {unlabeled:,} | P1: {'running' if ret1 is None else f'exited({ret1})'} | P2: {'running' if ret2 is None else f'exited({ret2})'}")
    
    if ret1 is not None and ret2 is not None:
        print("Both pipelines finished!")
        break

print(f"\nFinal: {labeled:,} images labeled in {elapsed/60:.1f} minutes")
log1.close()
log2.close()
