# site.yml
- hosts: compute
  become: true
  vars:
    slurm_conf_src: files/slurm.conf
  tasks:
    - name: Install node_exporter
      ansible.builtin.dnf:
        name: golang-github-prometheus-node-exporter
        state: present

    - name: Push slurm.conf
      ansible.builtin.copy:
        src: "{{ slurm_conf_src }}"
        dest: /etc/slurm/slurm.conf
        mode: "0644"
      notify: restart slurmd

    - name: Ensure slurmd running
      ansible.builtin.service:
        name: slurmd
        state: started
        enabled: true

  handlers:
    - name: restart slurmd
      ansible.builtin.service:
        name: slurmd
        state: restarted