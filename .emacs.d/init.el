(require 'package)
(add-to-list 'package-archives '("melpa" . "https://melpa.org/packages/") t)

;; https://www.reddit.com/r/emacs/comments/53zpv9/how_do_i_get_emacs_to_stop_adding_custom_fields/
(setq custom-file (expand-file-name "custom.el" user-emacs-directory))
(when (file-exists-p custom-file)
  (load custom-file))

(package-initialize)

;; install package-selected-packages defined in custom.el
(unless package-archive-contents
  (package-refresh-contents))
(package-install-selected-packages)

(load-theme 'tango-dark' t)  ;; theme

(setq inhibit-startup-screen t)  ;; disable startup screen
(setq initial-scratch-message "")  ;; set empty message to scratch
(tool-bar-mode -1)  ;; disable Toolbar
(menu-bar-mode -1)  ;; disable Menubar
(set-scroll-bar-mode nil)  ;; disable the display of scroll bars
(setq frame-title-format (format "%%f" (system-name)))  ;; show current buffer file path
(global-display-line-numbers-mode)  ;; display line number

(global-hl-line-mode t)  ;; highlight current line
(custom-set-faces
 '(hl-line ((t (:background "black")))))

(show-paren-mode t)  ;; show the matching parenthesis
(setq show-paren-style 'expression)
(setq show-paren-delay 0)
(set-face-attribute 'show-paren-match nil
                    :background nil :underline "gray50")

(set-face-attribute 'fringe nil :background "#2e3436") ;; right fringe background color

(electric-pair-mode 1)  ;; complete parentesis

(setq display-time-24hr-format t)
(display-time-mode 1)

;; set cursor style and color
(add-to-list 'default-frame-alist '(cursor-type . bar))
(add-to-list 'default-frame-alist '(cursor-color . "#ff9200"))

;; font
(when (member "Liberation Mono" (font-family-list))
  (add-to-list 'default-frame-alist '(font . "Liberation Mono 10")))

(setq-default line-spacing 1)

;; show useless whitespace at the end of a line
(defun my/show-trailing-whitespace-hook ()
  (setq show-trailing-whitespace t))
(add-hook 'prog-mode-hook 'my/show-trailing-whitespace-hook)

(defun my/delete-trailing-whitespace-hook ()
  (add-to-list 'write-file-functions 'delete-trailing-whitespace))

(defalias 'yes-or-no-p 'y-or-n-p)

(setq make-backup-files nil)  ;; disable to create backup~ files
(setq auto-save-default nil)  ;; disable to create #autosave# files
(setq create-lockfiles nil)  ;; disable to create .#lock files

(global-auto-revert-mode 1)
(setq ring-bell-function 'ignore)

(setq-default indent-tabs-mode nil)

(desktop-save-mode 1)

(setq confirm-kill-emacs 'yes-or-no-p)

;; keymap
(global-set-key (kbd "C-h") 'delete-backward-char)
(global-set-key (kbd "C-?") 'help)

;; ref: https://www.emacswiki.org/emacs/WindMove
(global-set-key (kbd "C-c <left>")  'windmove-left)
(global-set-key (kbd "C-c <right>") 'windmove-right)
(global-set-key (kbd "C-c <up>")    'windmove-up)
(global-set-key (kbd "C-c <down>")  'windmove-down)

;; fix slow next-line ref: https://emacs.stackexchange.com/questions/28736/emacs-pointcursor-movement-lag
(setq auto-window-vscroll nil)

(when (eq system-type 'darwin)
  (setq mac-command-modifier 'meta)
  (setq mac-option-modifier 'alt))

;; packages
(eval-when-compile
  (require 'use-package))

(require 'use-package-ensure)
(setq use-package-always-ensure t)

(use-package yasnippet
  :config (yas-global-mode t)
  :diminish 'yas-minor-mode)

(use-package hiwin
  :config
  (hiwin-activate)
  (set-face-background 'hiwin-face "gray32"))

(use-package ido
  :config
  (ido-mode t)
  (ido-everywhere t)
  (ido-vertical-mode t)
  (setq ido-vertical-define-keys 'C-n-and-C-p-only)
  (set-face-attribute 'ido-vertical-first-match-face nil
                      :foreground "orange")
  (set-face-attribute 'ido-subdir nil
                      :foreground "deep sky blue"))

(use-package smex
  :bind
  ("M-x" . smex)
  ("M-X" . smex-major-mode-commands)
  ("C-c C-c M-x" . execute-extended-command)
  :config
  (smex-initialize)
  (defun smex-prepare-ido-bindings ()
    (define-key ido-completion-map (kbd "C-h") 'delete-backward-char)))

(use-package flycheck
  :bind
  ("C-c n" . flycheck-next-error)
  ("C-c p" . flycheck-previous-error)
  :config
  (global-flycheck-mode)
  (setq-default flycheck-disabled-checkers '(emacs-lisp-checkdoc)))

(use-package mozc
  :config
  (setq default-input-method "japanese-mozc")
  (setq mozc-candidate-style 'echo-area))

(use-package markdown-mode
  :commands (markdown-mode gfm-mode)
  :mode (("README\\.md\\'" . gfm-mode)
         ("\\.md\\'" . markdown-mode))
  :config
  (setq markdown-command "multimarkdown"))
  ;; (defun my/auto-fix-markdown ()
  ;;   (interactive)
  ;;   (call-process-shell-command
  ;;    (format "markdownlint -c ~/.markdownlint.yaml -f %s" buffer-file-name)
  ;;    nil "*Shell Command Output*" t)
  ;;   (shell-command (format "markdown-toc --maxdepth 4 --bullets '-' -i %s" buffer-file-name))
  ;;   (revert-buffer t t))
  ;; (eval-after-load 'markdown-mode
  ;;   '(add-hook 'markdown-mode-hook (lambda () (add-hook 'after-save-hook 'my/auto-fix-markdown)))))

(use-package grip-mode
  :custom
  (grip-command 'go-grip)
  (grip-theme 'dark)
  :bind (:map markdown-mode-command-map
         ("g" . grip-mode))
  :after markdown-mode)

(use-package powerline
  :config
  (powerline-default-theme)
  (set-face-attribute 'mode-line nil
                      :background "DarkOrange")
  (setq powerline-default-separator 'box))

(use-package yaml-mode
  :mode ("\\.ya?ml\\'" . yaml-mode)
  :hook (yaml-mode . my/delete-trailing-whitespace-hook))

(use-package vimrc-mode
  :mode "\\.vim\\(rc\\)?\\'")

(use-package powershell)

(use-package org
  :custom
  (system-time-locale "C")
  (org-clock-clocktable-default-properties '(:maxlevel 3))
  (org-adapt-indentation nil)
  (org-edit-src-content-indentation 0))

(use-package editorconfig
  :config
  (editorconfig-mode 1)
  :diminish editorconfig-mode)

(use-package multiple-cursors
  :bind
  ("C->" . mc/mark-next-like-this)
  ("C-<" . mc/mark-previous-like-this)
  ("C-c C-<" . mc/mark-all-like-this))

(use-package magit)

(use-package diminish
  :config
  (diminish 'eldoc-mode))

(use-package git-gutter
  :config
  (global-git-gutter-mode t)
  :diminish 'git-gutter-mode)

(use-package rainbow-mode
  :hook (web-mode html-mode css-mode js-mode emacs-lisp-mode)
  :diminish 'rainbow-mode)

(use-package highlight-indent-guides
  :hook (yaml-mode . highlight-indent-guides-mode)
  :custom (highlight-indent-guides-method 'column)
  :diminish 'highlight-indent-guides-mode)

(use-package undo-tree
  :config
  (global-undo-tree-mode)
  (unbind-key "C-?" undo-tree-map)
  (add-to-list 'undo-tree-history-directory-alist
			   (cons "." (concat user-emacs-directory "/undo-tree")))
  :diminish 'undo-tree-mode)
